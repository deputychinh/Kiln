import { Button, ICON_SIZE, TextField } from '@kiln/ui';
import { useNavigate } from '@tanstack/react-router';
import { CircleAlert, Info } from 'lucide-react';
import { type FormEvent, type ReactElement, useEffect, useRef, useState } from 'react';

import { isApiError } from '@/api/client';
import { LogoMark } from '@/components/LogoMark/LogoMark';
import { ThemeToggle } from '@/components/ThemeToggle/ThemeToggle';
import { AUTH_CODE } from '@/constants/auth.constant';
import { useSignIn } from '@/features/auth/hooks/useAuth';
import { useCopy } from '@/hooks/useCopy';
import { useDocumentTitle } from '@/hooks/useDocumentTitle';
import type { SignInFieldErrors as FieldErrors } from '@/interfaces/auth.interface';
import type { Copy } from '@/interfaces/copy.interface';
import { describeError } from '@/utils/error.util';
import { safeRedirect } from '@/utils/redirect.util';

import './SignInPage.css';

interface SignInPageProps {
  /** Where to go once signed in (checked: only a path on this app). */
  redirect?: string | undefined;
  /** The session ended while the person was working: say so above the form. */
  isExpired?: boolean;
}

const HTTP_FORBIDDEN = 403;
// Light check only: the API decides, and answers wrong and unknown accounts the same way.
const EMAIL_SHAPE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/u;

const validate = (email: string, password: string, copy: Copy): FieldErrors => {
  const trimmed = email.trim();
  return {
    ...(trimmed === '' ? { email: copy.auth.emailRequired } : {}),
    ...(trimmed !== '' && !EMAIL_SHAPE.test(trimmed) ? { email: copy.auth.emailInvalid } : {}),
    ...(password === '' ? { password: copy.auth.passwordRequired } : {}),
  };
};

const failureOf = (error: unknown, copy: Copy): string => {
  if (isApiError(error) && error.code === AUTH_CODE.invalidCredentials) {
    return copy.auth.invalidCredentials;
  }
  if (isApiError(error) && error.code === AUTH_CODE.throttled) return copy.auth.throttled;
  if (isApiError(error) && error.status === HTTP_FORBIDDEN) return copy.auth.blocked;
  return describeError(error, copy);
};

/** Email and password, centred on the page; there is no sign-up (accounts come from the admin). */
export const SignInPage = ({ redirect, isExpired = false }: SignInPageProps): ReactElement => {
  const copy = useCopy();
  const navigate = useNavigate();
  const signIn = useSignIn();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<FieldErrors>({});
  const headingRef = useRef<HTMLHeadingElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  useDocumentTitle(copy.auth.pageTitle);

  useEffect(() => headingRef.current?.focus(), []);

  const submit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (signIn.isPending) return;
    const found = validate(email, password, copy);
    setErrors(found);
    if (found.email) {
      emailRef.current?.focus();
      return;
    }
    if (found.password) {
      passwordRef.current?.focus();
      return;
    }
    signIn.mutate(
      { email: email.trim(), password },
      {
        onSuccess: () => void navigate({ href: safeRedirect(redirect), replace: true }),
        onError: () => {
          setPassword('');
          passwordRef.current?.focus();
        },
      },
    );
  };

  return (
    <div className="sign-in-page">
      <div className="sign-in-page__theme">
        <ThemeToggle />
      </div>
      <main id="main" className="sign-in-page__main">
        <div className="sign-in-page__brand">
          <LogoMark />
          <span className="sign-in-page__wordmark">{copy.app.name}</span>
        </div>
        <section className="sign-in-page__card" aria-labelledby="sign-in-title">
          <h1 id="sign-in-title" className="sign-in-page__title" ref={headingRef} tabIndex={-1}>
            {copy.auth.title}
          </h1>
          <p className="sign-in-page__lead">{copy.auth.lead}</p>
          {isExpired && !signIn.isError ? (
            <p className="sign-in-page__notice" role="status">
              <Info size={ICON_SIZE.sm} aria-hidden="true" />
              {copy.auth.signedOutNotice}
            </p>
          ) : null}
          <div className="sign-in-page__alert-slot" role="alert">
            {signIn.isError ? (
              <p className="sign-in-page__alert">
                <CircleAlert size={ICON_SIZE.sm} aria-hidden="true" />
                {failureOf(signIn.error, copy)}
              </p>
            ) : null}
          </div>
          <form className="sign-in-page__form" noValidate onSubmit={submit}>
            <TextField
              ref={emailRef}
              label={copy.auth.email}
              type="email"
              name="email"
              autoComplete="username"
              inputMode="email"
              autoCapitalize="none"
              spellCheck={false}
              required
              value={email}
              error={errors.email}
              onChange={(event) => setEmail(event.target.value)}
            />
            <TextField
              ref={passwordRef}
              label={copy.auth.password}
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              error={errors.password}
              onChange={(event) => setPassword(event.target.value)}
            />
            <Button type="submit" className="sign-in-page__submit" aria-disabled={signIn.isPending}>
              {signIn.isPending ? copy.auth.submitting : copy.auth.submit}
            </Button>
          </form>
        </section>
        <p className="sign-in-page__note">{copy.auth.noAccount}</p>
      </main>
    </div>
  );
};
