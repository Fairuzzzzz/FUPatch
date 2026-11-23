#!/usr/bin/env python3
"""Non-invasive LLDB touch tracer for the MHFU arm64 executable.

Import this file inside an LLDB session:
    command script import /path/to/mhfu_touch_trace.py

The script reads registers and stack frames only. It never dereferences target
pointers, writes target memory, or changes the game executable.
"""

import json
import math
import os
import shlex
import struct
import sys
import time

try:
    import lldb
except ImportError:  # Allows unit tests to import the pure helper functions.
    lldb = None


PREFERRED_BASE = 0x100000000
EXPECTED_UUID = '58cc55c760ca3196b5d20c2aeb64b32b'
EXECUTABLE_BASENAME = 'MH Unite'

# Addresses are unslid Mach-O virtual addresses from the verified
# iphone12-14 executable. Do not replace these with a session-specific slide.
TOUCH_SITES = (
    ('touchesBegan', 0x10046328C, ('x0', 'x1', 'x2', 'x3', 'x4', 'x5')),
    ('touchesMoved', 0x100463478, ('x0', 'x1', 'x2', 'x3', 'x4', 'x5')),
    ('touchesEnded', 0x1004635F8, ('x0', 'x1', 'x2', 'x3', 'x4', 'x5')),
    ('getTouchInfoIndex', 0x1004637A4, ('x0', 'x1')),
)

# These are after the locationInView: Objective-C calls in touchesBegan/Moved.
# On arm64, CGPoint is returned in d0/d1. Capture is optional and only reads
# those registers; it does not read the UITouch or view pointers.
POINT_SITES = (
    ('touchLocationBegan', 0x100463374, ('x0', 'x1', 'x2', 'x3')),
    ('touchLocationMoved', 0x10046354C, ('x0', 'x1', 'x2', 'x3')),
)

CONVERSION_SITES = (
    ('convertTouchBegan', 0x100460A24, ('x0', 'x1', 'x2', 'x3', 'x4', 'x5')),
    ('convertTouchMoved', 0x10046085C, ('x0', 'x1', 'x2', 'x3')),
    ('copyTouchPoint', 0x100461C0C, ('x0', 'x1')),
)

# Native point-in-rectangle predicate used by the input subsystem. The first
# site records its arguments; the second is the shared return path where x0
# contains the predicate's result. This is a candidate probe, not a menu label.
NATIVE_HIT_TEST_SITES = (
    ('nativeRectTest', 0x100460D44, ('x0', 'x1', 'x2', 'x30')),
    ('nativeRectTestResult', 0x100460D98, ('x0', 'x19', 'x20')),
)

MAX_EVENTS_LIMIT = 1000
MAX_STACK_LIMIT = 20

_STATE = {
    'debugger': None,
    'target': None,
    'module': None,
    'slide': None,
    'breakpoints': {},
    'site_metadata': {},
    'active': None,
    'last_session': None,
    'sessions': {},
}


def runtime_address(unslid_address, slide):
    """Translate a link-time virtual address using the current image slide."""
    return int(unslid_address) + int(slide)


def calculate_slide(unslid_address, runtime_address_value):
    """Return the ASLR slide from a verified unslid/runtime address pair."""
    return int(runtime_address_value) - int(unslid_address)


def _normal_uuid(value):
    return ''.join(ch for ch in (value or '').lower() if ch in '0123456789abcdef')


def _file_spec_fullpath(spec):
    """Return an SBFileSpec path without relying on GetPath() bindings."""
    if not spec or not spec.IsValid():
        return None
    try:
        path = spec.fullpath
        if callable(path):
            path = path()
        if path:
            return str(path)
    except Exception:
        pass
    try:
        directory = spec.GetDirectory() or ''
        filename = spec.GetFilename() or ''
        if directory and filename:
            return os.path.join(directory, filename)
        return filename or directory or None
    except Exception:
        return None


def _decode_float_register(raw_value):
    """Decode LLDB's scalar-register display when it is a decimal or 64-bit hex."""
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    try:
        if text.lower().startswith('0x'):
            bits = int(text, 16)
            if bits <= 0xFFFFFFFFFFFFFFFF:
                value = struct.unpack('<d', struct.pack('<Q', bits))[0]
                if math.isfinite(value):
                    return value
                return None
        value = float(text)
        return value if math.isfinite(value) else None
    except (ValueError, OverflowError, struct.error):
        return None


def summarize_events(events):
    """Summarize recorded events without inferring which UI element was hit."""
    counts = {}
    points = []
    stacks = {}
    for event in events or []:
        kind = event.get('kind', 'unknown')
        counts[kind] = counts.get(kind, 0) + 1
        point = event.get('point')
        if point and isinstance(point.get('x'), (int, float)) and \
                isinstance(point.get('y'), (int, float)):
            points.append((point['x'], point['y']))
        stack = event.get('stack') or []
        top = stack[0].get('function') if stack else None
        if top:
            stacks[top] = stacks.get(top, 0) + 1
    point_summary = None
    if points:
        point_summary = {
            'count': len(points),
            'mean_x': sum(p[0] for p in points) / len(points),
            'mean_y': sum(p[1] for p in points) / len(points),
            'first': {'x': points[0][0], 'y': points[0][1]},
            'last': {'x': points[-1][0], 'y': points[-1][1]},
        }
    return {
        'event_count': len(events or []),
        'by_kind': counts,
        'points': point_summary,
        'top_frame_counts': stacks,
    }


def status_snapshot(state):
    """Keep the last stopped-session count visible in status output."""
    active = state.get('active')
    last = state.get('last_session')
    if active is not None:
        label = active.get('label')
        count = len(active.get('events') or [])
        mode = 'recording'
    elif last is not None:
        label = last.get('label')
        count = last.get('event_count', 0)
        mode = 'stopped'
    else:
        label = None
        count = 0
        mode = 'idle'
    return {
        'state': mode,
        'label': label,
        'events': count,
        'last_session': last,
        'recorded_labels': sorted(state.get('sessions', {}).keys()),
    }


def compare_sessions(first, second):
    """Compare two event lists; this reports observations, not menu attribution."""
    left = summarize_events(first)
    right = summarize_events(second)
    lp, rp = left['points'], right['points']
    point_delta = None
    if lp and rp:
        point_delta = {
            'mean_x_second_minus_first': rp['mean_x'] - lp['mean_x'],
            'mean_y_second_minus_first': rp['mean_y'] - lp['mean_y'],
        }
    return {
        'first': left,
        'second': right,
        'point_delta': point_delta,
        'interpretation': (
            'Coordinate and call-stack differences are observations only; '
            'they do not prove a menu hit-test or rendering relationship.'
        ),
    }


def _require_lldb():
    if lldb is None:
        raise RuntimeError(
            'This command must run inside LLDB; only helper functions are '
            'available in ordinary Python.')


def _report(result, message, error=False):
    if error:
        result.SetError(str(message))
    else:
        result.AppendMessage(str(message))


def _find_game_module(target):
    matches = []
    for index in range(target.GetNumModules()):
        module = target.GetModuleAtIndex(index)
        if not module or not module.IsValid():
            continue
        spec = module.GetFileSpec()
        filename = spec.GetFilename() if spec and spec.IsValid() else ''
        if filename and filename.lower() == EXECUTABLE_BASENAME.lower():
            matches.append(module)
    if len(matches) != 1:
        raise RuntimeError(
            'Expected one loaded MH Unite module; found %d' % len(matches))
    module = matches[0]
    triple = module.GetTriple() or ''
    arch = triple.split('-', 1)[0].lower()
    if arch not in ('arm64', 'arm64e', 'aarch64'):
        raise RuntimeError('MH Unite is not an arm64 image: %s' % triple)
    actual_uuid = _normal_uuid(module.GetUUIDString())
    if actual_uuid != EXPECTED_UUID:
        raise RuntimeError(
            'MH Unite UUID mismatch: expected %s, found %s'
            % (EXPECTED_UUID, actual_uuid or '<unavailable>'))
    return module


def _resolve_address(target, module, unslid_address):
    file_address = module.ResolveFileAddress(int(unslid_address))
    if not file_address or not file_address.IsValid():
        raise RuntimeError('address %s is not in MH Unite'
                           % hex(unslid_address))
    load_address = file_address.GetLoadAddress(target)
    invalid = getattr(lldb, 'LLDB_INVALID_ADDRESS', 0xFFFFFFFFFFFFFFFF)
    if load_address == invalid:
        raise RuntimeError('address %s has no loaded address'
                           % hex(unslid_address))
    return int(load_address)


def _read_register(frame, name):
    """Read a register value as text; never dereference register contents."""
    try:
        value = frame.FindRegister(name)
        if not value or not value.IsValid():
            return None
        return value.GetValue()
    except Exception:
        return None


def _stack_snapshot(thread, depth):
    stack = []
    try:
        count = min(thread.GetNumFrames(), depth)
        for index in range(count):
            frame = thread.GetFrameAtIndex(index)
            if not frame or not frame.IsValid():
                continue
            module = frame.GetModule()
            spec = module.GetFileSpec() if module and module.IsValid() else None
            filename = spec.GetFilename() if spec and spec.IsValid() else None
            stack.append({
                'index': index,
                'pc': '0x%x' % frame.GetPC(),
                'function': frame.GetFunctionName() or '<no-symbol>',
                'module': filename,
            })
    except Exception:
        pass
    return stack


def _write_jsonl(path, record):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, 'a', encoding='utf-8') as stream:
        stream.write(json.dumps(record, sort_keys=True, ensure_ascii=True) + '\n')
        stream.flush()


def _prepare_log_path(path):
    folder = os.path.dirname(path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    # Fail before installing breakpoints if the selected log path is unusable.
    with open(path, 'a', encoding='utf-8'):
        pass


def _finish_session(reason):
    session = _STATE.get('active')
    if session is None:
        return
    session['stopped'] = time.time()
    session['stop_reason'] = reason
    _write_jsonl(session['path'], {
        'type': 'session_end',
        'label': session['label'],
        'session_id': session['session_id'],
        'time': session['stopped'],
        'event_count': len(session['events']),
        'reason': reason,
    })
    _STATE['last_session'] = {
        'label': session['label'],
        'session_id': session['session_id'],
        'event_count': len(session['events']),
        'path': session['path'],
        'stop_reason': reason,
        'stopped': session['stopped'],
    }
    _STATE['active'] = None
    for breakpoint in _STATE['breakpoints'].values():
        try:
            breakpoint.SetEnabled(False)
        except Exception:
            pass


def _breakpoint_callback(frame, breakpoint_location, internal_dict):
    """Record a bounded event and auto-continue; never stops the game."""
    try:
        session = _STATE.get('active')
        site = _callback_for_location(breakpoint_location)
        if session is None or site is None:
            return False

        now_mono = time.monotonic()
        if site['kind'] == 'touchesMoved' or site['kind'] == 'touchLocationMoved':
            last = session['last_move_by_kind'].get(site['kind'], 0.0)
            if now_mono - last < session['move_interval']:
                return False
            session['last_move_by_kind'][site['kind']] = now_mono
        elif site.get('rate_limited'):
            last = session['last_move_by_kind'].get(site['kind'], 0.0)
            if now_mono - last < session['native_interval']:
                return False
            session['last_move_by_kind'][site['kind']] = now_mono

        if len(session['events']) >= session['max_events']:
            _finish_session('max-events')
            return False

        thread = frame.GetThread()
        target = _STATE.get('target')
        runtime_pc = frame.GetPC()
        unslid_pc = runtime_pc - _STATE.get('slide', 0)
        registers = {}
        for name in site['registers']:
            registers[name] = _read_register(frame, name)

        point = None
        if site.get('point_registers'):
            raw = {
                name: _read_register(frame, name)
                for name in site['point_registers']
            }
            point = {
                'raw': raw,
                'x': _decode_float_register(raw.get('d0')),
                'y': _decode_float_register(raw.get('d1')),
            }

        event = {
            'type': 'event',
            'label': session['label'],
            'session_id': session['session_id'],
            'sequence': len(session['events']) + 1,
            'kind': site['kind'],
            'address_unslid': '0x%x' % site['unslid'],
            'address_runtime': '0x%x' % runtime_pc,
            'pc_unslid_observed': '0x%x' % unslid_pc,
            'thread_id': int(thread.GetThreadID()) if thread else None,
            'registers': registers,
            'point': point,
            'stack': _stack_snapshot(thread, session['stack_depth'])
            if thread else [],
            'time': time.time(),
        }
        session['events'].append(event)
        _write_jsonl(session['path'], event)
        if len(session['events']) >= session['max_events']:
            _finish_session('max-events')
        return False
    except Exception as exc:
        session = _STATE.get('active')
        if session is not None:
            try:
                _write_jsonl(session['path'], {
                    'type': 'tracer_error',
                    'label': session['label'],
                    'error': str(exc),
                    'time': time.time(),
                })
            except Exception:
                pass
        return False


def _delete_breakpoints():
    target = _STATE.get('target')
    if target and target.IsValid():
        for breakpoint in list(_STATE['breakpoints'].values()):
            try:
                target.BreakpointDelete(breakpoint.GetID())
            except Exception:
                pass
    _STATE['breakpoints'] = {}
    _STATE['site_metadata'] = {}
    _STATE['module'] = None
    _STATE['slide'] = None


def _sites_for_options(options):
    """Choose the UIKit trace or the opt-in native rectangle-probe trace."""
    if options.get('native_hit_test'):
        return [
            (kind, address, registers, True)
            for kind, address, registers in NATIVE_HIT_TEST_SITES
        ]
    sites = [(kind, address, registers, False) for kind, address, registers
             in TOUCH_SITES]
    if options.get('capture_points'):
        sites.extend((kind, address, registers, False)
                     for kind, address, registers in POINT_SITES)
    if options.get('include_conversion'):
        sites.extend((kind, address, registers, False)
                     for kind, address, registers in CONVERSION_SITES)
    return sites


def _install_breakpoints(debugger, target, module, slide, options):
    sites = _sites_for_options(options)
    created = {}
    try:
        for kind, unslid, registers, rate_limited in sites:
            address = _resolve_address(target, module, unslid)
            breakpoint = target.BreakpointCreateByAddress(address)
            if not breakpoint or not breakpoint.IsValid():
                raise RuntimeError('could not create breakpoint at %s'
                                   % hex(address))
            breakpoint.SetScriptCallbackFunction(
                __name__ + '._breakpoint_callback')
            try:
                breakpoint.SetAutoContinue(True)
            except Exception:
                # The callback returns False, which also requests continue.
                pass
            if breakpoint.GetNumLocations() < 1:
                target.BreakpointDelete(breakpoint.GetID())
                raise RuntimeError('breakpoint at %s has no locations'
                                   % hex(address))
            created[breakpoint.GetID()] = {
                'breakpoint': breakpoint,
                'kind': kind,
                'unslid': int(unslid),
                'registers': registers,
                'rate_limited': rate_limited,
                'point_registers': ('d0', 'd1')
                if kind in ('touchLocationBegan', 'touchLocationMoved')
                else (),
            }
        _STATE['debugger'] = debugger
        _STATE['target'] = target
        _STATE['module'] = module
        _STATE['slide'] = int(slide)
        _STATE['breakpoints'] = {
            bp_id: value['breakpoint'] for bp_id, value in created.items()
        }
        # Store callback metadata separately so LLDB callbacks need not inspect
        # target memory or parse breakpoint names.
        _STATE['site_metadata'] = {
            bp_id: {k: v for k, v in value.items() if k != 'breakpoint'}
            for bp_id, value in created.items()
        }
        return created
    except Exception:
        for breakpoint in created.values():
            try:
                target.BreakpointDelete(breakpoint['breakpoint'].GetID())
            except Exception:
                pass
        raise


def _callback_for_location(breakpoint_location):
    try:
        breakpoint = breakpoint_location.GetBreakpoint()
        if breakpoint and breakpoint.IsValid():
            return _STATE.get('site_metadata', {}).get(breakpoint.GetID())
    except Exception:
        pass
    return None


def _parse_start(command):
    tokens = shlex.split(command)
    if not tokens or tokens[0].startswith('--'):
        raise ValueError(
            'usage: mhfu-touch-start LABEL [--path PATH] [--max-events N] '
            '[--stack-depth N] [--move-interval SECONDS] '
            '[--include-conversion] [--no-points] [--native-hit-test] '
            '[--native-interval SECONDS]')
    label = tokens.pop(0)
    options = {
        'path': os.path.join(os.path.expanduser('~'), 'mhfu-touch-trace.jsonl'),
        'max_events': 100,
        'stack_depth': 8,
        'move_interval': 0.05,
        'capture_points': True,
        'include_conversion': False,
        'native_hit_test': False,
        'native_interval': 0.10,
    }
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in ('--path', '--max-events', '--stack-depth',
                     '--move-interval', '--native-interval'):
            if i + 1 >= len(tokens):
                raise ValueError('%s requires a value' % token)
            value = tokens[i + 1]
            if token == '--path':
                options['path'] = os.path.abspath(os.path.expanduser(value))
            elif token == '--max-events':
                options['max_events'] = min(MAX_EVENTS_LIMIT, max(1, int(value)))
            elif token == '--stack-depth':
                options['stack_depth'] = min(MAX_STACK_LIMIT, max(0, int(value)))
            elif token == '--move-interval':
                options['move_interval'] = min(5.0, max(0.0, float(value)))
            else:
                options['native_interval'] = min(5.0, max(0.0, float(value)))
            i += 2
        elif token == '--include-conversion':
            options['include_conversion'] = True
            i += 1
        elif token == '--no-points':
            options['capture_points'] = False
            i += 1
        elif token == '--native-hit-test':
            options['native_hit_test'] = True
            i += 1
        elif token in ('-h', '--help'):
            raise ValueError(
                'usage: mhfu-touch-start LABEL [--path PATH] [--max-events N] '
                '[--stack-depth N] [--move-interval SECONDS] '
                '[--include-conversion] [--no-points] [--native-hit-test] '
                '[--native-interval SECONDS]')
        else:
            raise ValueError('unknown option: %s' % token)
    return label, options


def lldb_start(debugger, command, result, internal_dict):
    try:
        _require_lldb()
        if _STATE.get('active') is not None:
            raise RuntimeError('a trace is already active; stop it first')
        label, options = _parse_start(command)
        if label in _STATE['sessions']:
            raise RuntimeError('label already recorded; choose another label')
        _prepare_log_path(options['path'])
        target = debugger.GetSelectedTarget()
        if not target or not target.IsValid():
            raise RuntimeError('no valid LLDB target is selected')
        module = _find_game_module(target)
        anchor = module.ResolveFileAddress(TOUCH_SITES[0][1])
        if not anchor or not anchor.IsValid():
            raise RuntimeError('cannot resolve the known touch entry in MH Unite')
        loaded = anchor.GetLoadAddress(target)
        invalid = getattr(lldb, 'LLDB_INVALID_ADDRESS', 0xFFFFFFFFFFFFFFFF)
        if loaded == invalid:
            raise RuntimeError('the touch entry has no loaded address')
        slide = calculate_slide(TOUCH_SITES[0][1], loaded)
        _delete_breakpoints()
        created = _install_breakpoints(debugger, target, module, slide, options)
        session = dict(options)
        session.update({
            'label': label,
            'session_id': '%s-%d' % (label, int(time.time() * 1000)),
            'started': time.time(),
            'events': [],
            'last_move_by_kind': {},
        })
        _STATE['active'] = session
        _STATE['sessions'][label] = session['events']
        try:
            _write_jsonl(session['path'], {
                'type': 'session_start',
                'label': label,
                'session_id': session['session_id'],
                'path': session['path'],
                'module': _file_spec_fullpath(module.GetFileSpec()),
                'uuid': module.GetUUIDString(),
                'mode': 'native-hit-test' if options['native_hit_test']
                else 'ui-touch',
                'preferred_base': '0x%x' % PREFERRED_BASE,
                'slide': '0x%x' % slide,
                'breakpoints': [
                    {'kind': item['kind'], 'unslid': '0x%x' % item['unslid']}
                    for item in created.values()
                ],
                'time': session['started'],
            })
        except Exception:
            _STATE['active'] = None
            _STATE['sessions'].pop(label, None)
            _delete_breakpoints()
            raise
        _report(result, 'Tracing %s; slide=%s; %d breakpoints; log=%s'
                % (label, hex(slide), len(created), session['path']))
    except Exception as exc:
        _report(result, str(exc), error=True)


def lldb_stop(debugger, command, result, internal_dict):
    if _STATE.get('active') is None:
        _report(result, 'No trace is active.')
        return
    label = _STATE['active']['label']
    _finish_session('user-stop')
    _report(result, 'Stopped trace %s.' % label)


def lldb_status(debugger, command, result, internal_dict):
    target = _STATE.get('target')
    info = status_snapshot(_STATE)
    info.update({
        'breakpoint_ids': sorted(_STATE.get('breakpoints', {}).keys()),
        'slide': '0x%x' % _STATE['slide'] if _STATE.get('slide') is not None else None,
        'target_valid': bool(target and target.IsValid()),
    })
    _report(result, json.dumps(info, indent=2))


def lldb_show(debugger, command, result, internal_dict):
    try:
        tokens = shlex.split(command)
        if not tokens:
            raise ValueError('usage: mhfu-touch-show LABEL [LIMIT]')
        label = tokens[0]
        limit = min(100, max(1, int(tokens[1]))) if len(tokens) > 1 else 20
        events = _STATE.get('sessions', {}).get(label)
        if events is None:
            raise ValueError('no recorded session named %s' % label)
        _report(result, json.dumps(events[-limit:], indent=2))
    except Exception as exc:
        _report(result, str(exc), error=True)


def lldb_compare(debugger, command, result, internal_dict):
    try:
        tokens = shlex.split(command)
        if len(tokens) != 2:
            raise ValueError('usage: mhfu-touch-compare LABEL_A LABEL_B')
        first, second = tokens
        sessions = _STATE.get('sessions', {})
        if first not in sessions or second not in sessions:
            raise ValueError('both labels must be recorded in this LLDB session')
        _report(result, json.dumps(
            compare_sessions(sessions[first], sessions[second]), indent=2))
    except Exception as exc:
        _report(result, str(exc), error=True)


def lldb_remove(debugger, command, result, internal_dict):
    if _STATE.get('active') is not None:
        _finish_session('breakpoints-removed')
    count = len(_STATE.get('breakpoints', {}))
    _delete_breakpoints()
    _report(result, 'Removed %d tracer-created breakpoints.' % count)


def __lldb_init_module(debugger, internal_dict):
    """Register the LLDB commands when imported with `command script import`."""
    module_name = __name__
    commands = (
        ('lldb_start', 'mhfu-touch-start'),
        ('lldb_stop', 'mhfu-touch-stop'),
        ('lldb_status', 'mhfu-touch-status'),
        ('lldb_show', 'mhfu-touch-show'),
        ('lldb_compare', 'mhfu-touch-compare'),
        ('lldb_remove', 'mhfu-touch-remove'),
    )
    for function, name in commands:
        debugger.HandleCommand(
            'command script add -f %s.%s %s' % (module_name, function, name))
    print('MHFU touch tracer loaded. Run `mhfu-touch-start --help` for usage.')
