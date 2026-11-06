import type { components } from '@/api/kiln.schema';

type Schemas = components['schemas'];

export type Asset = Schemas['AssetOut'];
export type AssetDetail = Schemas['AssetDetailOut'];
export type AssetPage = Schemas['AssetPageOut'];
export type AssetVersion = Schemas['VersionOut'];
export type AssetKind = Schemas['AssetKind'];
export type VersionStatus = Schemas['VersionStatus'];
export type FailureReason = Schemas['FailureReason'];
