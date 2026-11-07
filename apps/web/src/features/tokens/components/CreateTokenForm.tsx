import { Button, ICON_SIZE, SegmentedControl, TextField } from '@kiln/ui';
import { KeyRound } from 'lucide-react';
import { type FormEvent, type ReactElement, useId, useRef, useState } from 'react';

import {
  DEFAULT_TOKEN_LIFETIME,
  TOKEN_LIFETIMES,
  TOKEN_NAME_MAX_LENGTH,
} from '@/constants/auth.constant';
import { TokenAccess } from '@/enums/token-access.enum';
import { useCreateToken } from '@/features/tokens/hooks/useTokens';
import { useCopy } from '@/hooks/useCopy';
import type { CreatedToken, TokenLifetime } from '@/interfaces/auth.interface';
import { scopesFor } from '@/utils/auth.util';
import { describeError } from '@/utils/error.util';

import './CreateTokenForm.css';

interface CreateTokenFormProps {
  /** The new token, whose secret the page shows once. */
  onCreated: (token: CreatedToken) => void;
}

const isLifetime = (value: string): value is `${TokenLifetime}` =>
  TOKEN_LIFETIMES.some((days) => String(days) === value);

/** Name, access and lifetime of a new personal access token. */
export const CreateTokenForm = ({ onCreated }: CreateTokenFormProps): ReactElement => {
  const copy = useCopy();
  const create = useCreateToken();
  const formId = useId();
  const [name, setName] = useState('');
  const [access, setAccess] = useState<TokenAccess>(TokenAccess.ReadWrite);
  const [lifetime, setLifetime] = useState<`${TokenLifetime}`>(
    String(DEFAULT_TOKEN_LIFETIME) as `${TokenLifetime}`,
  );
  const [nameError, setNameError] = useState<string | undefined>();
  const nameRef = useRef<HTMLInputElement>(null);

  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (create.isPending) return;
    const trimmed = name.trim();
    const error =
      trimmed === ''
        ? copy.settings.nameRequired
        : trimmed.length > TOKEN_NAME_MAX_LENGTH
          ? copy.settings.nameTooLong(TOKEN_NAME_MAX_LENGTH)
          : undefined;
    setNameError(error);
    if (error) {
      nameRef.current?.focus();
      return;
    }
    create.mutate(
      {
        name: trimmed,
        scopes: scopesFor(access),
        expires_in_days: Number(lifetime) as TokenLifetime,
      },
      {
        onSuccess: (token) => {
          setName('');
          onCreated(token);
        },
      },
    );
  };

  return (
    <form
      className="create-token-form"
      noValidate
      onSubmit={submit}
      aria-labelledby={`${formId}-title`}
    >
      <h3 id={`${formId}-title`} className="create-token-form__title">
        {copy.settings.createTitle}
      </h3>
      <TextField
        ref={nameRef}
        className="create-token-form__name"
        label={copy.settings.name}
        hint={copy.settings.nameHint}
        autoComplete="off"
        value={name}
        error={nameError}
        onChange={(event) => setName(event.target.value)}
      />
      <div className="create-token-form__choices">
        <SegmentedControl
          label={copy.settings.access}
          name={`${formId}-access`}
          value={access}
          options={[
            { value: TokenAccess.Read, label: copy.settings.accessRead },
            { value: TokenAccess.ReadWrite, label: copy.settings.accessReadWrite },
          ]}
          onChange={setAccess}
        />
        <SegmentedControl
          label={copy.settings.lifetime}
          name={`${formId}-lifetime`}
          value={lifetime}
          options={TOKEN_LIFETIMES.map((days) => ({
            value: String(days) as `${TokenLifetime}`,
            label: copy.settings.lifetimeDays(days),
          }))}
          onChange={(value) => {
            if (isLifetime(value)) setLifetime(value);
          }}
        />
      </div>
      <div role="alert" className="create-token-form__alert">
        {create.isError
          ? `${copy.settings.createFailed}: ${describeError(create.error, copy)}`
          : null}
      </div>
      <Button
        type="submit"
        className="create-token-form__submit"
        icon={<KeyRound size={ICON_SIZE.sm} />}
        aria-disabled={create.isPending}
      >
        {create.isPending ? copy.settings.creating : copy.settings.create}
      </Button>
    </form>
  );
};
