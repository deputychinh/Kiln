import {
  Group,
  Mesh,
  MeshBasicMaterial,
  PerspectiveCamera,
  BoxGeometry,
  Spherical,
  Vector3,
} from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

import {
  PAN_STEP_RATIO,
  ROTATE_STEP_RADIANS,
  VIEW_FIT_MARGIN,
  VIEW_FOV_DEGREES,
  VIEW_MAX_DISTANCE_RADII,
  VIEW_MIN_DISTANCE_RADII,
  ZOOM_STEP_FACTOR,
} from '@/constants/viewer.constant';
import { ViewerError } from '@/enums/viewer-error.enum';
import { createViewerController, frameObject } from '@/features/viewer/services/scene.service';
import { viewerErrorOf } from '@/utils/viewer.util';

const box = (at = new Vector3()): Group => {
  const group = new Group();
  const mesh = new Mesh(new BoxGeometry(2, 2, 2), new MeshBasicMaterial());
  mesh.position.copy(at);
  group.add(mesh);
  return group;
};

const setUp = (object = box()) => {
  const camera = new PerspectiveCamera(VIEW_FOV_DEGREES, 1);
  const controls = new OrbitControls(camera, document.createElement('div'));
  const invalidate = vi.fn();
  frameObject(object, camera, controls);
  const controller = createViewerController({ camera, controls, invalidate });
  return { camera, controls, invalidate, controller };
};

const offsetOf = (camera: PerspectiveCamera, controls: OrbitControls): Spherical =>
  new Spherical().setFromVector3(camera.position.clone().sub(controls.target));

const RADIUS = Math.sqrt(3);
const FRAMED_DISTANCE = (RADIUS / Math.sin((VIEW_FOV_DEGREES * Math.PI) / 360)) * VIEW_FIT_MARGIN;

describe('frameObject', () => {
  it('fits the bounding sphere in view from three-quarters above, aimed at its centre', () => {
    const { camera, controls } = setUp(box(new Vector3(10, 0, 0)));

    expect(controls.target.toArray()).toEqual([10, 0, 0]);
    expect(camera.position.distanceTo(controls.target)).toBeCloseTo(FRAMED_DISTANCE, 5);
    const offset = camera.position.clone().sub(controls.target);
    expect(offset.x).toBeGreaterThan(0);
    expect(offset.y).toBeGreaterThan(0);
    expect(offset.z).toBeGreaterThan(offset.x); // 35° round, so more in front than to the side
    expect(controls.minDistance).toBeCloseTo(RADIUS * VIEW_MIN_DISTANCE_RADII);
    expect(controls.maxDistance).toBeCloseTo(RADIUS * VIEW_MAX_DISTANCE_RADII);
    expect(camera.far).toBeGreaterThan(controls.maxDistance + RADIUS);
  });

  it('fits by the narrower side on a tall, thin view', () => {
    const camera = new PerspectiveCamera(VIEW_FOV_DEGREES, 0.5);
    const controls = new OrbitControls(camera, document.createElement('div'));
    frameObject(box(), camera, controls);
    expect(camera.position.distanceTo(controls.target)).toBeGreaterThan(FRAMED_DISTANCE);
  });

  it('refuses a model with nothing to show', () => {
    const camera = new PerspectiveCamera(VIEW_FOV_DEGREES, 1);
    const controls = new OrbitControls(camera, document.createElement('div'));
    let error: unknown = null;
    try {
      frameObject(new Group(), camera, controls);
    } catch (caught) {
      error = caught;
    }
    expect(viewerErrorOf(error)).toBe(ViewerError.Unreadable);
  });
});

describe('the viewer controller', () => {
  it('rotates by one step round the model, keeping the distance, and asks for a frame', () => {
    const { camera, controls, invalidate, controller } = setUp();
    const before = offsetOf(camera, controls);

    controller.rotate(1, 0);

    const after = offsetOf(camera, controls);
    expect(after.theta - before.theta).toBeCloseTo(ROTATE_STEP_RADIANS);
    expect(after.phi).toBeCloseTo(before.phi);
    expect(after.radius).toBeCloseTo(before.radius);
    expect(invalidate).toHaveBeenCalled();
  });

  it('tilts up and down without going over the top', () => {
    const { camera, controls, controller } = setUp();
    const before = offsetOf(camera, controls);

    controller.rotate(0, 1);
    expect(offsetOf(camera, controls).phi - before.phi).toBeCloseTo(ROTATE_STEP_RADIANS);

    controller.rotate(0, -100);
    const top = offsetOf(camera, controls);
    expect(top.phi).toBeGreaterThan(0);
    expect(top.phi).toBeLessThan(0.01);
  });

  it('zooms in and out by one step, within the distance limits', () => {
    const { camera, controls, controller } = setUp();
    const distance = () => camera.position.distanceTo(controls.target);

    controller.zoom(1);
    expect(distance()).toBeCloseTo(FRAMED_DISTANCE / ZOOM_STEP_FACTOR);
    controller.zoom(-2);
    expect(distance()).toBeCloseTo(FRAMED_DISTANCE * ZOOM_STEP_FACTOR);
    controller.zoom(-100);
    expect(distance()).toBeCloseTo(controls.maxDistance);
    controller.zoom(100);
    expect(distance()).toBeCloseTo(controls.minDistance);
  });

  it('moves the model right and up on screen by a tenth of the distance', () => {
    const { camera, controls, controller } = setUp();
    camera.updateMatrix();
    const right = new Vector3().setFromMatrixColumn(camera.matrix, 0);
    const up = new Vector3().setFromMatrixColumn(camera.matrix, 1);
    const target = controls.target.clone();
    const offset = camera.position.clone().sub(target);

    controller.pan(1, 1);

    const step = FRAMED_DISTANCE * PAN_STEP_RATIO;
    const expected = target.clone().addScaledVector(right, -step).addScaledVector(up, -step);
    expect(controls.target.distanceTo(expected)).toBeCloseTo(0);
    expect(camera.position.clone().sub(controls.target).distanceTo(offset)).toBeCloseTo(0);
  });

  it('resets to the framed view after any change', () => {
    const { camera, controls, controller } = setUp();
    const position = camera.position.clone();
    const target = controls.target.clone();

    controller.rotate(2, 1);
    controller.zoom(3);
    controller.pan(-1, 2);
    controller.reset();

    expect(camera.position.distanceTo(position)).toBeCloseTo(0);
    expect(controls.target.distanceTo(target)).toBeCloseTo(0);
  });
});
