import { ICON_SIZE, IconButton, IconButtonSize, TooltipPlacement } from '@kiln/ui';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { type ReactElement, useCallback, useId, useState } from 'react';

import { UPLOAD_BUTTON_ID } from '@/constants/upload.constant';
import { UploadList } from '@/features/uploads/components/UploadList';
import { useUploadQueue } from '@/features/uploads/context/UploadsContext';
import { useCopy } from '@/hooks/useCopy';
import { uploadSummaryOf } from '@/utils/upload-summary.util';

import './UploadTray.css';

/**
 * New-asset uploads in a tray in the bottom corner, on every page: the summary stays in view,
 * the rows can be collapsed, and new files open it again. Hidden while there is nothing to show.
 */
export const UploadTray = (): ReactElement => {
  const copy = useCopy();
  const uploads = useUploadQueue();
  const titleId = useId();
  const bodyId = useId();
  const items = uploads.items.filter((item) => item.targetAssetId === null);
  // Collapsed "at" a row count: adding files (more rows than then) opens the tray again.
  const [collapsedAt, setCollapsedAt] = useState<number | null>(null);
  const isCollapsed = collapsedAt !== null && items.length <= collapsedAt;
  const summary = uploadSummaryOf(items);
  const focusUploadButton = useCallback(() => document.getElementById(UPLOAD_BUTTON_ID), []);

  return (
    <section className="upload-tray" aria-labelledby={titleId} hidden={items.length === 0}>
      <div className="upload-tray__head">
        <h2 id={titleId} className="upload-tray__title">
          {copy.uploads.listLabel}
        </h2>
        <p className="upload-tray__summary">
          {copy.uploads.summary(summary.finished, summary.total, summary.failed)}
        </p>
        <IconButton
          label={isCollapsed ? copy.uploads.trayExpand : copy.uploads.trayCollapse}
          icon={
            isCollapsed ? <ChevronUp size={ICON_SIZE.md} /> : <ChevronDown size={ICON_SIZE.md} />
          }
          size={IconButtonSize.Small}
          tooltipPlacement={TooltipPlacement.Top}
          aria-expanded={!isCollapsed}
          aria-controls={bodyId}
          onClick={() => setCollapsedAt(isCollapsed ? null : items.length)}
        />
      </div>
      <div id={bodyId} className="upload-tray__body" hidden={isCollapsed}>
        <UploadList
          uploads={uploads}
          listLabel={copy.uploads.listLabel}
          hasSummary={false}
          fallbackFocus={focusUploadButton}
        />
      </div>
    </section>
  );
};
