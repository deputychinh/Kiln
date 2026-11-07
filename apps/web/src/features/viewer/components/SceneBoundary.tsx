import { Component, type ReactNode } from 'react';

import type { ViewerError } from '@/enums/viewer-error.enum';
import { sceneErrorOf } from '@/utils/viewer.util';

interface SceneBoundaryProps {
  children: ReactNode;
  onError: (error: ViewerError) => void;
}

/**
 * Catches what the lazily loaded scene throws: its chunk failing to load (`SceneLoad`, retryable)
 * or three.js failing to parse or draw (`Unreadable`), so the viewer shows why over the preview
 * instead of the route's error page.
 */
// eslint-disable-next-line no-restricted-syntax -- React catches render errors only in a class component (getDerivedStateFromError); there is no hook for it
export class SceneBoundary extends Component<SceneBoundaryProps, { hasFailed: boolean }> {
  override state = { hasFailed: false };

  static getDerivedStateFromError(): { hasFailed: boolean } {
    return { hasFailed: true };
  }

  override componentDidCatch(error: unknown): void {
    this.props.onError(sceneErrorOf(error));
  }

  override render(): ReactNode {
    return this.state.hasFailed ? null : this.props.children;
  }
}
