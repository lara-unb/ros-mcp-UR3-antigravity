import asyncio
import csv
import math
import os
import sys
import time

print(f"script_start_unix={time.time():.9f}", flush=True)
COMPUTE_START = time.perf_counter()
try:
    import numpy as np
except ImportError as exc:
    raise SystemExit(f"Missing dependency; no installation attempted: {exc}")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../shared')))
from ur3_controller import UR3Controller, HOME_JOINTS

A = [0, -0.24365, -0.21325, 0, 0, 0]
D = [0.1519, 0, 0, 0.11235, 0.08535, 0.0819]
ALPHA = [math.pi / 2, 0, 0, math.pi / 2, -math.pi / 2, 0]
HOME = np.array(HOME_JOINTS, dtype=float)


def fk(q, jacobian=False):
    t = np.eye(4)
    origins, axes = [], []
    for theta, a, d, alpha in zip(q, A, D, ALPHA):
        origins.append(t[:3, 3].copy())
        axes.append(t[:3, 2].copy())
        c, s = math.cos(theta), math.sin(theta)
        ca, sa = math.cos(alpha), math.sin(alpha)
        t = t @ np.array([[c, -s*ca, s*sa, a*c],
                          [s, c*ca, -c*sa, a*s],
                          [0, sa, ca, d], [0, 0, 0, 1]])
    if not jacobian:
        return t
    j = np.column_stack([np.r_[np.cross(z, t[:3, 3]-o), z]
                         for o, z in zip(origins, axes)])
    return t, j


def rotation_error(target, actual):
    r = target @ actual.T
    v = np.array([r[2, 1]-r[1, 2], r[0, 2]-r[2, 0], r[1, 0]-r[0, 1]]) / 2
    s = np.linalg.norm(v)
    angle = math.atan2(s, np.clip((np.trace(r)-1)/2, -1, 1))
    if angle > 3.0:
        raise ValueError('Unexpected large orientation error')
    return v if s < 1e-12 else v * angle/s


def inverse(p, orientation, seed):
    q = seed.copy()
    for _ in range(180):
        t, j = fk(q, True)
        error = np.r_[p-t[:3, 3], rotation_error(orientation, t[:3, :3])]
        if np.linalg.norm(error[:3]) < 1e-6 and np.linalg.norm(error[3:]) < 1e-6:
            return q
        damping = 0.00002
        step = j.T @ np.linalg.solve(j @ j.T + damping**2*np.eye(6), error)
        step *= min(1.0, 0.10/max(np.max(np.abs(step)), 1e-15))
        norm = np.linalg.norm(error)
        for scale in (1, .5, .25, .125, .0625, .03125):
            candidate = q + scale*step
            ft = fk(candidate)
            e = np.r_[p-ft[:3, 3], rotation_error(orientation, ft[:3, :3])]
            if np.linalg.norm(e) < norm:
                q = candidate
                break
        else:
            raise ValueError(f'DLS stalled at target {p.tolist()}; reachability unproven')
    raise ValueError(f'DLS did not converge at {p.tolist()}; reachability unproven')


CURVES = np.array([[[0, 0], [-.02, -.01], [-.06, -.005], [-.06, -.025]],
                   [[-.06, -.025], [-.06, -.05], [0, -.05], [0, -.075]],
                   [[0, -.075], [0, -.10], [-.04, -.09], [-.06, -.10]]])


def letter(u):
    segment = min(int(u*3), 2)
    v = u*3-segment
    b = CURVES[segment]
    return (1-v)**3*b[0] + 3*(1-v)**2*v*b[1] + 3*(1-v)*v*v*b[2] + v**3*b[3]


def plan(initial, cap):
    home_t = fk(HOME)
    orientation = home_t[:3, :3]
    start = fk(initial)
    if np.linalg.norm(rotation_error(orientation, start[:3, :3])) > 1e-4:
        raise ValueError('Current orientation conflicts with fixed Home orientation; no motion sent')
    origin = start[:3, 3]
    forward = orientation[:, 2]
    up = np.array([0., 0., 1.])
    right = np.cross(forward, up)
    right /= np.linalg.norm(right)
    if abs(np.dot(forward, up)) > 1e-4:
        raise ValueError('Home wall is not vertical under the supplied conventions')
    parameters = np.linspace(0, 1, 1201)
    qs = [initial.copy()]
    for u in parameters[1:]:
        xy = letter(u)
        target = origin + right*xy[0] + up*xy[1]
        solution = inverse(target, orientation, qs[-1])
        if np.max(np.abs(solution-qs[-1])) > .20:
            raise ValueError('IK continuity rejection')
        qs.append(solution)
    qs = np.array(qs)
    if np.max(np.abs(qs)) > 2*math.pi:
        raise ValueError('Joint limit rejection')
    dt = 1.875*np.max(np.abs(np.diff(qs, axis=0)), axis=1)/(.8*cap) + .005
    times = np.r_[0, np.cumsum(dt)]
    secants = np.diff(qs, axis=0)/dt[:, None]
    slopes = np.zeros_like(qs)
    for i in range(1, len(qs)-1):
        slopes[i] = (dt[i]*secants[i-1] + dt[i-1]*secants[i])/(dt[i-1]+dt[i])
    print(f'IK_path_planning_seconds={time.perf_counter()-PLAN_START:.6f}', flush=True)
    validation_start = time.perf_counter()
    points = []
    max_position_error = max_rotation_error = max_speed = 0.
    for i, h in enumerate(dt):
        count = max(1, math.ceil(h/.025))
        for k in range(count + (i == len(dt)-1)):
            s = k/count
            q = ((2*s**3-3*s*s+1)*qs[i] + (s**3-2*s*s+s)*h*slopes[i]
                 + (-2*s**3+3*s*s)*qs[i+1] + (s**3-s*s)*h*slopes[i+1])
            velocity = ((6*s*s-6*s)*qs[i]/h + (3*s*s-4*s+1)*slopes[i]
                        + (-6*s*s+6*s)*qs[i+1]/h + (3*s*s-2*s)*slopes[i+1])
            t = fk(q)
            xy = letter(parameters[i]*(1-s)+parameters[i+1]*s)
            target = origin + right*xy[0] + up*xy[1]
            pe = np.linalg.norm(t[:3, 3]-target)
            re = np.linalg.norm(rotation_error(orientation, t[:3, :3]))
            max_position_error = max(max_position_error, pe)
            max_rotation_error = max(max_rotation_error, re)
            max_speed = max(max_speed, float(np.max(np.abs(velocity))))
            if pe > 1e-4 or re > 1e-4 or np.max(np.abs(q)) > 2*math.pi:
                raise ValueError(f'Interpolated path rejected: position error {pe}, rotation error {re}')
            nanoseconds = round((times[i]+s*h)*1e9)
            points.append({'positions': q.tolist(), 'velocities': velocity.tolist(),
                           'time_from_start': {'sec': nanoseconds//1000000000,
                                               'nanosec': nanoseconds % 1000000000}})
    if max_speed >= cap or not np.array_equal(np.array(points[0]['positions']), initial):
        raise ValueError('Speed or exact current-state start rejection')
    if max(abs(v) for v in points[0]['velocities']+points[-1]['velocities']) > 1e-10:
        raise ValueError('Nonzero endpoint speed')
    if np.linalg.norm(fk(np.array(points[0]['positions']))[:3, 3]-origin) > 1e-10:
        raise ValueError('Drawing start mismatch')
    if times[-1] > 40 and cap <= .15:
        raise ValueError('Physical trajectory exceeds 40 seconds')
    print(f'origin_base_m={origin.tolist()} forward={forward.tolist()} '
          f'right={right.tolist()} wall_offset_m={np.dot(forward, origin):.6f}', flush=True)
    print(f'S: 0.06 m wide, 0.10 m high, starts upper-right at current flange, extends down/left; '
          f'Home orientation fixed; flange centre traces; speed_cap={cap} rad/s', flush=True)
    print(f'max_FK_position_error_m={max_position_error:.9g} '
          f'max_orientation_error_rad={max_rotation_error:.9g} max_joint_speed={max_speed:.6f}', flush=True)
    return points, float(times[-1]), validation_start


async def main():
    global PLAN_START
    controller = UR3Controller()
    telemetry = {'file': None, 'writer': None, 'rows': 0, 'path': None, 'active': False}

    def record(stamp, positions, physical):
        if not physical or not telemetry['active']:
            return
        if telemetry['file'] is None:
            os.makedirs('telemetry', exist_ok=True)
            path = f'telemetry/telemetry_S_{int(stamp)}.csv'
            telemetry['file'] = open(path, 'x', newline='')
            telemetry['path'] = path
            telemetry['writer'] = csv.writer(telemetry['file'])
            telemetry['writer'].writerow(['timestamp', 'source', 'shoulder_pan', 'shoulder_lift',
                                         'elbow', 'wrist_1', 'wrist_2', 'wrist_3'])
        telemetry['writer'].writerow([f'{stamp:.9f}', 'UR3_Real']+[repr(v) for v in positions])
        telemetry['rows'] += 1

    controller.add_joint_state_callback(record)
    try:
        detection_start = time.perf_counter()
        await controller.connect()
        try:
            measured = await controller.fetch_current_state()
        except RuntimeError:
            if controller.physical_seen:
                raise
            measured = None
        physical = controller.physical_seen
        initial = np.array(measured if physical else HOME, dtype=float)
        print(f'state_detection_seconds={time.perf_counter()-detection_start:.6f}', flush=True)
        print('target=physical UR3 (simulation presence unknown)' if physical else
              'target=simulation-only: no physical /joint_states received; assuming Home', flush=True)
        if physical and time.time()-controller.last_physical_msg_time > 1:
            raise RuntimeError('Physical state is stale')
        PLAN_START = time.perf_counter()
        points, duration, validation_start = await asyncio.to_thread(plan, initial, controller.max_joint_speed)
        controller.validate_trajectory(points)
        print(f'trajectory_validation_seconds={time.perf_counter()-validation_start:.6f}', flush=True)
        await asyncio.sleep(.1)
        if not physical and controller.physical_seen:
            raise RuntimeError('Physical robot appeared after simulation decision; aborting before publish')
        if physical:
            if not controller.connected or time.time()-controller.last_physical_msg_time > 1:
                raise RuntimeError('Physical state stopped arriving; aborting before publish')
            if np.max(np.abs(np.array(controller.current_joints)-initial)) > .01:
                raise RuntimeError('Physical arm moved during planning')
            samples = []
            def resting(stamp, joints, is_physical):
                if is_physical:
                    samples.append(joints)
            controller.add_joint_state_callback(resting)
            await asyncio.sleep(.25)
            if len(samples) < 2 or np.max(np.ptp(np.array(samples), axis=0)) > .002:
                raise RuntimeError('Physical arm is not confirmed at rest')
        if not physical and controller.physical_seen:
            raise RuntimeError('Physical robot appeared; aborting before publish')
        telemetry['active'] = physical
        print(f'total_compute_before_publish_seconds={time.perf_counter()-COMPUTE_START:.6f}', flush=True)
        await controller.publish_trajectory(points)
        print(f'trajectory_published_unix={time.time():.9f} duration_s={duration:.6f} points={len(points)}', flush=True)
        await asyncio.sleep(duration+1)
        print(f'motion_finished_unix={time.time():.9f}', flush=True)
        if physical:
            if not controller.connected or time.time()-controller.last_physical_msg_time > 1:
                raise RuntimeError('Physical feedback lost; completion unconfirmed')
            gap = np.max(np.abs(np.array(controller.current_joints)-np.array(points[-1]['positions'])))
            if gap > .02:
                raise RuntimeError(f'Final physical joints differ by {gap:.6f} rad; completion unconfirmed')
            print('completion=confirmed from physical joints', flush=True)
        else:
            print('completion=unconfirmed: simulator publishes no feedback; no telemetry CSV created. '
                  'Stop/start CoppeliaSim before the next task to restore Home.', flush=True)
    finally:
        telemetry['active'] = False
        if telemetry['file']:
            telemetry['file'].close()
            print(f"telemetry_csv={telemetry['path']} rows={telemetry['rows']}", flush=True)
        await controller.shutdown()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except Exception as exc:
        print(f'ABORT: {type(exc).__name__}: {exc}', flush=True)
        sys.exit(1)
