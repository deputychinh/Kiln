import {
  Box3,
  MathUtils,
  type PerspectiveCamera,
  Sphere,
  Spherical,
  Vector3,
  type Object3D,
} from 'three';
import type { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';

import {
  PAN_STEP_RATIO,
  ROTATE_STEP_RADIANS,
  VIEW_FIT_MARGIN,
  VIEW_MAX_DISTANCE_RADII,
  VIEW_MIN_DISTANCE_RADII,
  VIEW_PITCH_RADIANS,
  VIEW_YAW_RADIANS,
  ZOOM_STEP_FACTOR,
} from '@/constants/viewer.constant';
import { ViewerError } from '@/enums/viewer-error.enum';
import type { ViewerController } from '@/interfaces/viewer.interface';
import { viewerFailure } from '@/utils/viewer.util';

/** Keeps the camera off the poles, where orbiting would flip it. */
const POLE_MARGIN = 1e-3;
const NEAR_RATIO = 0.01;

/**
 * Points the camera at the model's centre from the preview's angle, far enough for its bounding
 * sphere to fit the narrower side of the view, and saves that as the view Reset returns to.
 */
export const frameObject = (
  object: Object3D,
  camera: PerspectiveCamera,
  controls: OrbitControls,
): void => {
  const sphere = new Box3().setFromObject(object).getBoundingSphere(new Sphere());
  if (!Number.isFinite(sphere.radius) || sphere.radius <= 0) {
    throw viewerFailure(ViewerError.Unreadable);
  }
  const verticalHalf = MathUtils.degToRad(camera.fov) / 2;
  const horizontalHalf = Math.atan(Math.tan(verticalHalf) * camera.aspect);
  const distance =
    (sphere.radius / Math.sin(Math.min(verticalHalf, horizontalHalf))) * VIEW_FIT_MARGIN;
  const direction = new Vector3(
    Math.sin(VIEW_YAW_RADIANS) * Math.cos(VIEW_PITCH_RADIANS),
    Math.sin(VIEW_PITCH_RADIANS),
    Math.cos(VIEW_YAW_RADIANS) * Math.cos(VIEW_PITCH_RADIANS),
  );
  controls.minDistance = sphere.radius * VIEW_MIN_DISTANCE_RADII;
  controls.maxDistance = sphere.radius * VIEW_MAX_DISTANCE_RADII;
  camera.near = controls.minDistance * NEAR_RATIO;
  camera.far = (controls.maxDistance + sphere.radius) * 2;
  camera.position.copy(sphere.center).addScaledVector(direction, distance);
  camera.updateProjectionMatrix();
  controls.target.copy(sphere.center);
  controls.update();
  controls.saveState();
};

/**
 * The toolbar's and the keys' steps, applied straight to the camera so each press jumps (no
 * animation) the way a drag of the same direction would move it.
 */
export const createViewerController = ({
  camera,
  controls,
  invalidate,
}: {
  camera: PerspectiveCamera;
  controls: OrbitControls;
  invalidate: () => void;
}): ViewerController => {
  const settle = (): void => {
    controls.update();
    invalidate();
  };
  return {
    rotate: (x, y) => {
      const offset = camera.position.clone().sub(controls.target);
      const spherical = new Spherical().setFromVector3(offset);
      spherical.theta += x * ROTATE_STEP_RADIANS;
      spherical.phi = MathUtils.clamp(
        spherical.phi + y * ROTATE_STEP_RADIANS,
        POLE_MARGIN,
        Math.PI - POLE_MARGIN,
      );
      camera.position.copy(controls.target).add(offset.setFromSpherical(spherical));
      camera.lookAt(controls.target);
      settle();
    },
    pan: (x, y) => {
      camera.updateMatrix();
      const step = camera.position.distanceTo(controls.target) * PAN_STEP_RATIO;
      // The model goes right on screen when the camera goes left.
      const move = new Vector3()
        .addScaledVector(new Vector3().setFromMatrixColumn(camera.matrix, 0), -x * step)
        .addScaledVector(new Vector3().setFromMatrixColumn(camera.matrix, 1), -y * step);
      camera.position.add(move);
      controls.target.add(move);
      settle();
    },
    zoom: (steps) => {
      const offset = camera.position.clone().sub(controls.target);
      const distance = MathUtils.clamp(
        offset.length() / ZOOM_STEP_FACTOR ** steps,
        controls.minDistance,
        controls.maxDistance,
      );
      camera.position.copy(controls.target).add(offset.setLength(distance));
      settle();
    },
    reset: () => {
      // `reset()` keeps the inertia left by a drag, which would turn the view away again: one
      // undamped update spends it first (it clears what is left), then the framed view returns.
      const { enableDamping } = controls;
      controls.enableDamping = false;
      controls.update();
      controls.reset();
      controls.enableDamping = enableDamping;
      invalidate();
    },
  };
};
