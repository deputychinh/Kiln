import type { components } from '@/api/kiln.schema';
import type { assetDetailQueryKey } from '@/constants/assets.constant';

type Schemas = components['schemas'];

export type Asset = Schemas['AssetOut'];
export type AssetDetail = Schemas['AssetDetailOut'];
export type AssetPage = Schemas['AssetPageOut'];
export type AssetVersion = Schemas['VersionOut'];
export type AssetKind = Schemas['AssetKind'];
export type VersionStatus = Schemas['VersionStatus'];
export type FailureReason = Schemas['FailureReason'];

/** An asset's detail query as both the detail view and the upload queue run it. */
export interface AssetDetailQuery {
  queryKey: ReturnType<typeof assetDetailQueryKey>;
  queryFn: (context: { signal: AbortSignal }) => Promise<AssetDetail>;
  structuralSharing: (previous: unknown, next: unknown) => unknown;
}
