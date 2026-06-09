import { EMAIL_ALREADY_EXISTS_MESSAGE } from "../utils/authErrors";

interface Props {
  onSignIn: () => void;
  onForgotPassword: () => void;
}

export default function EmailExistsNotice({ onSignIn, onForgotPassword }: Props) {
  return (
    <div className="auth-email-exists" role="alert">
      <p>{EMAIL_ALREADY_EXISTS_MESSAGE}</p>
      <div className="auth-email-exists-actions">
        <button type="button" className="auth-primary-btn auth-primary-btn--compact" onClick={onSignIn}>
          Sign in
        </button>
        <button type="button" className="auth-link-btn" onClick={onForgotPassword}>
          Forgot password?
        </button>
      </div>
    </div>
  );
}
