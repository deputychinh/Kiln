import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { type ReactElement, useEffect, useEffectEvent, useMemo, useRef, useState } from 'react';
import { type Group, Material, Mesh, type PerspectiveCamera, PMREMGenerator, Texture } from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js';

import { VIEW_FOV_DEGREES } from '@/constants/viewer.constant';
import { ViewerError } from '@/enums/viewer-error.enum';
import { parseModel } from '@/features/viewer/services/gltf.service';
import { createViewerController, frameObject } from '@/features/viewer/services/scene.service';
import type { ModelSceneProps } from '@/interfaces/viewer.interface';
import { sceneErrorOf, viewerFailure } from '@/utils/viewer.util';
import { canUseWebGl } from '@/utils/webgl.util';

/** Blur of the studio environment: soft, neutral light from every side. */
const ENVIRONMENT_SIGMA = 0.04;
/**
 * The environment alone lights every face of a plain model alike; a dimmer environment and a key
 * light from above left and in front give its faces different shades, like the still preview.
 */
const ENVIRONMENT_INTENSITY = 0.6;
const KEY_LIGHT_INTENSITY = 2;
const KEY_LIGHT_DIRECTION: [number, number, number] = [-2, 4, 3];
const MAX_PIXEL_RATIO = 2;

/** Frees what the GPU holds for a model: geometries, materials and their textures. */
const disposeObject = (object: Group): void => {
  object.traverse((child) => {
    if (!(child instanceof Mesh)) return;
    const mesh = child as Mesh;
    mesh.geometry.dispose();
    const materials: unknown[] = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
    for (const material of materials) {
      if (!(material instanceof Material)) continue;
      for (const value of Object.values(material)) if (value instanceof Texture) value.dispose();
      material.dispose();
    }
  });
};

const SceneContent = ({
  model,
  isReducedMotion,
  onReady,
  onError,
}: ModelSceneProps): ReactElement => {
  const camera = useThree((state) => state.camera) as PerspectiveCamera;
  const gl = useThree((state) => state.gl);
  const invalidate = useThree((state) => state.invalidate);
  const [object, setObject] = useState<Group | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const fail = useEffectEvent((error: unknown) => onError(sceneErrorOf(error)));
  const ready = useEffectEvent(onReady);
  const reducedMotion = useEffectEvent(() => isReducedMotion);

  // A neutral studio: soft light from every side, no background (the stage shows through).
  const environment = useMemo(() => {
    const generator = new PMREMGenerator(gl);
    const room = new RoomEnvironment();
    const texture = generator.fromScene(room, ENVIRONMENT_SIGMA).texture;
    room.dispose();
    generator.dispose();
    return texture;
  }, [gl]);
  useEffect(() => () => environment.dispose(), [environment]);

  useEffect(() => {
    let isCurrent = true;
    let parsed: Group | null = null;
    parseModel(model).then(
      (group) => {
        if (!isCurrent) {
          disposeObject(group);
          return;
        }
        parsed = group;
        setObject(group);
      },
      (error: unknown) => {
        if (isCurrent) fail(error);
      },
    );
    return () => {
      isCurrent = false;
      if (parsed) disposeObject(parsed);
    };
  }, [model]);

  useEffect(() => {
    if (!object) return undefined;
    const controls = new OrbitControls(camera, gl.domElement);
    controls.enableDamping = !reducedMotion();
    const onChange = (): void => invalidate();
    controls.addEventListener('change', onChange);
    try {
      frameObject(object, camera, controls);
    } catch (error) {
      controls.dispose();
      fail(error);
      return undefined;
    }
    controlsRef.current = controls;
    ready(createViewerController({ camera, controls, invalidate }));
    invalidate();
    return () => {
      controlsRef.current = null;
      controls.removeEventListener('change', onChange);
      controls.dispose();
    };
  }, [object, camera, gl, invalidate]);

  // A context lost while the model is shown (GPU reset, too many contexts) ends the view; the
  // viewer keeps the first error it was told, and the listener goes with the model.
  useEffect(() => {
    if (!object) return undefined;
    const canvas = gl.domElement;
    const onLost = (): void => fail(viewerFailure(ViewerError.WebGl));
    canvas.addEventListener('webglcontextlost', onLost);
    return () => canvas.removeEventListener('webglcontextlost', onLost);
  }, [object, gl]);

  // Reduced motion: no inertia after a drag, so nothing keeps moving by itself.
  useEffect(() => {
    if (controlsRef.current) controlsRef.current.enableDamping = !isReducedMotion;
  }, [isReducedMotion]);

  // On-demand frames: damping asks for the next frame only while it is still settling.
  useFrame(() => {
    controlsRef.current?.update();
  });

  return (
    <>
      <primitive object={environment} attach="environment" />
      <directionalLight position={KEY_LIGHT_DIRECTION} intensity={KEY_LIGHT_INTENSITY} />
      {object ? <primitive object={object} /> : null}
    </>
  );
};

/** The WebGL scene; the only module that imports three.js, loaded lazily by `ModelViewer`. */
export const ModelScene = ({ onError, ...props }: ModelSceneProps): ReactElement | null => {
  const [isSupported] = useState(canUseWebGl);
  useEffect(() => {
    if (!isSupported) onError(ViewerError.WebGl);
  }, [isSupported, onError]);
  if (!isSupported) return null;
  return (
    // The stage around it carries the name and the keys; the canvas itself is only the drawing.
    <Canvas
      frameloop="demand"
      dpr={[1, MAX_PIXEL_RATIO]}
      camera={{ fov: VIEW_FOV_DEGREES }}
      onCreated={({ scene }) => {
        scene.environmentIntensity = ENVIRONMENT_INTENSITY;
      }}
    >
      <SceneContent {...props} onError={onError} />
    </Canvas>
  );
};
