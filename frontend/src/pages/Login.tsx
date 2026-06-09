import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api, clearTokens, setTokens } from "../api/client";
import EmailExistsNotice from "../components/EmailExistsNotice";
import { isEmailAlreadyExistsError, normalizeEmail } from "../utils/authErrors";

type View = "login" | "register" | "forgot";
type RegisterRole = "patient" | "doctor";

interface Specialization {
  id: string;
  name: string;
}

const REGISTER_STEPS_PATIENT = [
  { title: "Account Setup", subtitle: "Secure your access" },
  { title: "Personal Details", subtitle: "Basic identity" },
  { title: "Initial Health Profile", subtitle: "Medical history" },
];

const REGISTER_STEPS_DOCTOR = [
  { title: "Account Setup", subtitle: "Secure your access" },
  { title: "Professional Details", subtitle: "Doctor profile" },
];

export default function Login() {
  const [view, setView] = useState<View>("login");
  const [registerStep, setRegisterStep] = useState(1);
  const [registerRole, setRegisterRole] = useState<RegisterRole>("patient");
  const [specialties, setSpecialties] = useState<Specialization[]>([]);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [remember, setRemember] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);
  const [forgotStep, setForgotStep] = useState(1);
  const [resetOtp, setResetOtp] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmNewPassword, setConfirmNewPassword] = useState("");
  const [devResetOtp, setDevResetOtp] = useState("");
  const [forgotMessage, setForgotMessage] = useState("");

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [dob, setDob] = useState("");
  const [gender, setGender] = useState("");
  const [phone, setPhone] = useState("");
  const [allergies, setAllergies] = useState("");
  const [conditions, setConditions] = useState("");
  const [consent, setConsent] = useState(false);
  const [specialty, setSpecialty] = useState("General Physician");
  const [experienceYears, setExperienceYears] = useState("5");

  const [error, setError] = useState("");
  const [emailExists, setEmailExists] = useState(false);
  const [loading, setLoading] = useState(false);
  const nav = useNavigate();
  const location = useLocation();

  const registerSteps = registerRole === "doctor" ? REGISTER_STEPS_DOCTOR : REGISTER_STEPS_PATIENT;
  const totalSteps = registerSteps.length;

  useEffect(() => {
    clearTokens();
  }, []);

  useEffect(() => {
    const state = location.state as { view?: View; email?: string } | null;
    if (!state?.view && !state?.email) return;
    if (state.email) setEmail(state.email);
    if (state.view === "forgot") setView("forgot");
    else if (state.view === "login") setView("login");
    window.history.replaceState({}, document.title);
  }, [location.state]);

  useEffect(() => {
    if (view === "register") {
      api<Specialization[]>("/api/v1/doctors/specializations")
        .then((list) => {
          setSpecialties(list);
          if (list.length > 0) setSpecialty(list[0].name);
        })
        .catch(() =>
          setSpecialties([
            { id: "1", name: "General Physician" },
            { id: "2", name: "Cardiologist" },
            { id: "3", name: "Neurologist" },
            { id: "4", name: "Dermatologist" },
            { id: "5", name: "Pediatrician" },
          ])
        );
    }
  }, [view]);

  const redirectByRole = (role: string) => {
    if (role === "doctor") nav("/doctor");
    else if (role === "admin") nav("/admin");
    else nav("/dashboard");
  };

  const doLogin = async (skipRedirect = false) => {
    const tokens = await api<{ access_token: string; refresh_token: string }>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: normalizeEmail(email), password }),
    });
    setTokens(tokens.access_token, tokens.refresh_token);
    if (remember) localStorage.setItem("remember_device", "1");
    const me = await api<{ role: string; name: string }>("/api/v1/auth/me");
    localStorage.setItem("user_role", me.role);
    localStorage.setItem("user_name", me.name);
    if (!skipRedirect) redirectByRole(me.role);
    return me.role;
  };

  const saveOptionalHealthProfile = async () => {
    if (conditions.trim()) {
      await api("/api/v1/patients/me/medical-history", {
        method: "POST",
        body: JSON.stringify({ condition: conditions.trim(), notes: "Added during registration" }),
      }).catch(() => undefined);
    }
    if (allergies.trim()) {
      await api("/api/v1/patients/me/allergies", {
        method: "POST",
        body: JSON.stringify({ allergen: allergies.trim(), severity: "moderate" }),
      }).catch(() => undefined);
    }
  };

  const handleRegister = async () => {
    const normalizedEmail = normalizeEmail(email);
    const body: Record<string, unknown> = { name, email: normalizedEmail, password, role: registerRole };
    if (registerRole === "doctor") {
      body.specialty = specialty;
      body.experience_years = parseInt(experienceYears, 10) || 1;
    }
    await api("/api/v1/auth/register", { method: "POST", body: JSON.stringify(body) });
    await doLogin(true);
    if (registerRole === "patient") {
      await saveOptionalHealthProfile();
    }
    setShowSuccess(true);
    setTimeout(() => redirectByRole(registerRole), 1400);
  };

  const validateRegisterStep = (): string | null => {
    if (registerStep === 1) {
      if (!email.trim()) return "Email is required.";
      if (password.length < 8) return "Password must be at least 8 characters.";
      if (!/\d/.test(password)) return "Password must include at least one number.";
      if (password !== confirmPassword) return "Passwords do not match.";
    }
    if (registerStep === 2) {
      if (!name.trim() || name.trim().length < 2) return "Full name is required.";
      if (registerRole === "doctor" && !specialty) return "Specialty is required.";
    }
    if (registerStep === 3 && registerRole === "patient" && !consent) {
      return "Please consent to health data processing to continue.";
    }
    return null;
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await doLogin();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  };

  const handleRegisterNext = () => {
    const msg = validateRegisterStep();
    if (msg) {
      setError(msg);
      return;
    }
    setError("");
    if (registerStep < totalSteps) {
      setRegisterStep((s) => s + 1);
      return;
    }
    void submitRegister();
  };

  const submitRegister = async () => {
    const msg = validateRegisterStep();
    if (msg) {
      setError(msg);
      return;
    }
    setError("");
    setLoading(true);
    try {
      await handleRegister();
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Registration failed";
      if (isEmailAlreadyExistsError(errMsg)) {
        setEmailExists(true);
        setRegisterStep(1);
        setError("");
      } else {
        setEmailExists(false);
        setError(errMsg);
      }
    } finally {
      setLoading(false);
    }
  };

  const switchToRegister = () => {
    setView("register");
    setRegisterStep(1);
    setEmailExists(false);
    setError("");
  };

  const switchToLogin = () => {
    setView("login");
    setRegisterStep(1);
    setEmailExists(false);
    setForgotStep(1);
    setResetOtp("");
    setNewPassword("");
    setConfirmNewPassword("");
    setDevResetOtp("");
    setForgotMessage("");
    setError("");
  };

  const switchToForgot = () => {
    setView("forgot");
    setForgotStep(1);
    setError("");
    setForgotMessage("");
    setDevResetOtp("");
    setResetOtp("");
    setNewPassword("");
    setConfirmNewPassword("");
  };

  const sendPasswordResetCode = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email.trim()) {
      setError("Email is required.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await api<{ message: string; dev_otp?: string | null }>("/api/v1/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify({ email: normalizeEmail(email) }),
      });
      setForgotMessage(res.message);
      setDevResetOtp(res.dev_otp || "");
      setForgotStep(2);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not send reset code");
    } finally {
      setLoading(false);
    }
  };

  const submitPasswordReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (resetOtp.trim().length !== 6) {
      setError("Enter the 6-digit code from your email.");
      return;
    }
    if (newPassword.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (!/\d/.test(newPassword)) {
      setError("Password must include at least one number.");
      return;
    }
    if (newPassword !== confirmNewPassword) {
      setError("Passwords do not match.");
      return;
    }
    setError("");
    setLoading(true);
    try {
      const res = await api<{ message: string }>("/api/v1/auth/reset-password", {
        method: "POST",
        body: JSON.stringify({
          email: normalizeEmail(email),
          otp: resetOtp.trim(),
          new_password: newPassword,
        }),
      });
      setForgotMessage(res.message);
      setPassword(newPassword);
      setShowSuccess(true);
      setTimeout(() => {
        setShowSuccess(false);
        switchToLogin();
      }, 1800);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Password reset failed");
    } finally {
      setLoading(false);
    }
  };

  if (view === "forgot") {
    return (
      <div className="auth-shell auth-login-page">
        <div className="auth-login-bg" aria-hidden />
        <div className="auth-login-brand">
          <div className="auth-shield-logo">
            <span className="material-symbols-outlined">health_and_safety</span>
          </div>
          <h1>MediAI</h1>
          <p>AI-assisted health guidance and patient care workflows.</p>
        </div>

        <div className="auth-login-card">
          <h2>Reset Password</h2>
          <p className="auth-login-sub">
            {forgotStep === 1
              ? "Enter your account email and we will send a verification code."
              : "Enter the code from your email and choose a new password."}
          </p>

          {forgotStep === 1 ? (
            <form onSubmit={sendPasswordResetCode} className="auth-form">
              <label className="auth-field">
                <span>Email Address</span>
                <div className="auth-input-wrap">
                  <span className="material-symbols-outlined">mail</span>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@example.com"
                    required
                  />
                </div>
              </label>

              {error && <p className="auth-error">{error}</p>}

              <button type="submit" className="auth-primary-btn" disabled={loading}>
                {loading ? "Sending code..." : "Send Reset Code"}
                <span className="material-symbols-outlined">arrow_forward</span>
              </button>
            </form>
          ) : (
            <form onSubmit={submitPasswordReset} className="auth-form">
              {forgotMessage && <p className="auth-info-inline">{forgotMessage}</p>}
              {devResetOtp && (
                <p className="auth-dev-otp">
                  Dev mode code: <strong>{devResetOtp}</strong>
                </p>
              )}

              <label className="auth-field">
                <span>Verification Code</span>
                <div className="auth-input-wrap">
                  <span className="material-symbols-outlined">pin</span>
                  <input
                    type="text"
                    inputMode="numeric"
                    pattern="[0-9]{6}"
                    maxLength={6}
                    value={resetOtp}
                    onChange={(e) => setResetOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    placeholder="6-digit code"
                    required
                  />
                </div>
              </label>

              <label className="auth-field">
                <span>New Password</span>
                <div className="auth-input-wrap">
                  <span className="material-symbols-outlined">lock</span>
                  <input
                    type={showPassword ? "text" : "password"}
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    minLength={8}
                  />
                  <button
                    type="button"
                    className="auth-icon-btn"
                    onClick={() => setShowPassword((v) => !v)}
                    aria-label="Toggle password visibility"
                  >
                    <span className="material-symbols-outlined">{showPassword ? "visibility_off" : "visibility"}</span>
                  </button>
                </div>
              </label>

              <label className="auth-field">
                <span>Confirm New Password</span>
                <div className="auth-input-wrap">
                  <span className="material-symbols-outlined">lock</span>
                  <input
                    type={showConfirmPassword ? "text" : "password"}
                    value={confirmNewPassword}
                    onChange={(e) => setConfirmNewPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    minLength={8}
                  />
                  <button
                    type="button"
                    className="auth-icon-btn"
                    onClick={() => setShowConfirmPassword((v) => !v)}
                    aria-label="Toggle confirm password visibility"
                  >
                    <span className="material-symbols-outlined">{showConfirmPassword ? "visibility_off" : "visibility"}</span>
                  </button>
                </div>
              </label>

              {error && <p className="auth-error">{error}</p>}

              <button type="submit" className="auth-primary-btn" disabled={loading}>
                {loading ? "Updating..." : "Update Password"}
                <span className="material-symbols-outlined">check_circle</span>
              </button>

              <button
                type="button"
                className="auth-text-btn auth-text-btn--block"
                onClick={() => { setForgotStep(1); setError(""); }}
              >
                Resend code to a different email
              </button>
            </form>
          )}

          <p className="auth-switch">
            Remember your password?{" "}
            <button type="button" className="auth-link-btn" onClick={switchToLogin}>
              Back to Sign In
            </button>
          </p>
        </div>

        {showSuccess && (
          <div className="auth-success-modal">
            <div className="auth-success-card">
              <div className="auth-success-icon">
                <span className="material-symbols-outlined">task_alt</span>
              </div>
              <h2>Password Updated</h2>
              <p>Your password has been reset. Redirecting to sign in...</p>
            </div>
          </div>
        )}
      </div>
    );
  }

  if (view === "login") {
    return (
      <div className="auth-shell auth-login-page">
        <div className="auth-login-bg" aria-hidden />
        <div className="auth-login-brand">
          <div className="auth-shield-logo">
            <span className="material-symbols-outlined">health_and_safety</span>
          </div>
          <h1>MediAI</h1>
          <p>AI-assisted health guidance and patient care workflows.</p>
        </div>

        <div className="auth-login-card">
          <h2>Patient Login</h2>
          <p className="auth-login-sub">Welcome back. Sign in with your account email and password.</p>

          <form onSubmit={handleLoginSubmit} className="auth-form">
            <label className="auth-field">
              <span>Email Address</span>
              <div className="auth-input-wrap">
                <span className="material-symbols-outlined">mail</span>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  required
                />
              </div>
            </label>

            <label className="auth-field">
              <span className="auth-field-row">
                <span>Password</span>
                <button type="button" className="auth-text-btn" onClick={switchToForgot}>
                  Forgot password?
                </button>
              </span>
              <div className="auth-input-wrap">
                <span className="material-symbols-outlined">lock</span>
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  minLength={8}
                />
                <button
                  type="button"
                  className="auth-icon-btn"
                  onClick={() => setShowPassword((v) => !v)}
                  aria-label="Toggle password visibility"
                >
                  <span className="material-symbols-outlined">{showPassword ? "visibility_off" : "visibility"}</span>
                </button>
              </div>
            </label>

            <label className="auth-check">
              <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
              <span>Remember this device</span>
            </label>

            {error && <p className="auth-error">{error}</p>}

            <button type="submit" className="auth-primary-btn" disabled={loading}>
              {loading ? "Signing in..." : "Sign In to Portal"}
              <span className="material-symbols-outlined">arrow_forward</span>
            </button>
          </form>

          <div className="auth-divider">
            <span>Or continue with</span>
          </div>

          <div className="auth-social-row">
            <button type="button" className="auth-social-btn" disabled title="Demo only">
              <span className="auth-google-g">G</span> Google
            </button>
            <button type="button" className="auth-social-btn" disabled title="Demo only">
              <span className="material-symbols-outlined">groups</span> Meta Login
            </button>
          </div>

          <p className="auth-switch">
            Don&apos;t have a patient account?{" "}
            <button type="button" className="auth-link-btn" onClick={switchToRegister}>
              Request Access
            </button>
          </p>
        </div>

        <div className="auth-login-badges">
          <span><span className="material-symbols-outlined">verified_user</span> Secure Sign-In</span>
          <span><span className="material-symbols-outlined">shield</span> Privacy-Focused Design</span>
        </div>

        <div className="auth-insight-tip">
          <strong>Important</strong>
          <p>MediAI offers educational guidance only. Always consult a licensed clinician for diagnosis and treatment.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="auth-shell auth-register-page">
      <header className="auth-register-header">
        <div className="auth-register-header-inner">
          <div className="auth-brand-row">
            <span className="material-symbols-outlined">medical_services</span>
            <span>MediAI</span>
          </div>
          <div className="auth-header-links">
            <button type="button" className="auth-header-link">Help</button>
            <button type="button" className="auth-header-link">Support</button>
            <span className="auth-header-sep" />
            <button type="button" className="auth-header-link active" onClick={switchToLogin}>
              Sign In
            </button>
          </div>
        </div>
      </header>

      <main className="auth-register-main">
        <div className="auth-register-grid">
          <aside className="auth-register-side">
            <div>
              <h1>Join MediAI</h1>
              <p>Your journey to a smarter, personalized health experience starts here.</p>
            </div>

            <div className="auth-role-pick">
              <span>Register as</span>
              <div className="auth-role-btns">
                <button
                  type="button"
                  className={registerRole === "patient" ? "active" : ""}
                  onClick={() => { setRegisterRole("patient"); setRegisterStep(1); setError(""); }}
                >
                  Patient
                </button>
                <button
                  type="button"
                  className={registerRole === "doctor" ? "active" : ""}
                  onClick={() => { setRegisterRole("doctor"); setRegisterStep(1); setError(""); }}
                >
                  Doctor
                </button>
              </div>
            </div>

            <nav className="auth-stepper" aria-label="Registration progress">
              {registerSteps.map((step, idx) => {
                const num = idx + 1;
                const done = num < registerStep;
                const active = num === registerStep;
                return (
                  <div key={step.title} className={`auth-step-item ${active ? "active" : ""} ${done ? "done" : ""}`}>
                    <span className="auth-step-dot">
                      {done ? <span className="material-symbols-outlined">check</span> : num}
                    </span>
                    <div>
                      <strong>{step.title}</strong>
                      <span>{step.subtitle}</span>
                    </div>
                  </div>
                );
              })}
            </nav>

            <div className="auth-hipaa-card">
              <span className="material-symbols-outlined">verified_user</span>
              <strong>Your Data, Protected</strong>
              <p>Health information is stored securely and used to personalize your MediAI experience.</p>
            </div>
          </aside>

          <section className="auth-register-form-panel">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleRegisterNext();
              }}
            >
              {registerStep === 1 && (
                <div className="auth-step-panel">
                  <label className="auth-field plain">
                    <span>Email Address</span>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        setEmailExists(false);
                      }}
                      placeholder="name@example.com"
                      required
                    />
                  </label>
                  <label className="auth-field plain">
                    <span>Password</span>
                    <div className="auth-password-box">
                      <input
                        type={showPassword ? "text" : "password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        required
                        minLength={8}
                        autoComplete="new-password"
                      />
                      <button
                        type="button"
                        className="auth-password-toggle"
                        onClick={() => setShowPassword((v) => !v)}
                        aria-label="Toggle password visibility"
                      >
                        <span className="material-symbols-outlined">{showPassword ? "visibility_off" : "visibility"}</span>
                      </button>
                    </div>
                    <small className="auth-field-hint">Minimum 8 characters with at least one number.</small>
                  </label>
                  <label className="auth-field plain">
                    <span>Confirm Password</span>
                    <div className="auth-password-box">
                      <input
                        type={showConfirmPassword ? "text" : "password"}
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder="••••••••"
                        required
                        autoComplete="new-password"
                      />
                      <button
                        type="button"
                        className="auth-password-toggle"
                        onClick={() => setShowConfirmPassword((v) => !v)}
                        aria-label="Toggle confirm password visibility"
                      >
                        <span className="material-symbols-outlined">{showConfirmPassword ? "visibility_off" : "visibility"}</span>
                      </button>
                    </div>
                  </label>
                </div>
              )}

              {registerStep === 2 && registerRole === "patient" && (
                <div className="auth-step-panel">
                  <label className="auth-field plain">
                    <span>Full Name</span>
                    <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="John Doe" required />
                  </label>
                  <div className="auth-two-col">
                    <label className="auth-field plain">
                      <span>Date of Birth</span>
                      <input type="date" value={dob} onChange={(e) => setDob(e.target.value)} />
                    </label>
                    <label className="auth-field plain">
                      <span>Gender</span>
                      <select value={gender} onChange={(e) => setGender(e.target.value)}>
                        <option value="">Select gender</option>
                        <option value="male">Male</option>
                        <option value="female">Female</option>
                        <option value="other">Non-binary / Other</option>
                        <option value="prefer-not-to-say">Prefer not to say</option>
                      </select>
                    </label>
                  </div>
                  <label className="auth-field plain">
                    <span>Phone Number</span>
                    <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+1 (555) 000-0000" />
                  </label>
                </div>
              )}

              {registerStep === 2 && registerRole === "doctor" && (
                <div className="auth-step-panel">
                  <label className="auth-field plain">
                    <span>Full Name</span>
                    <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Dr. Your Name" required />
                  </label>
                  <label className="auth-field plain">
                    <span>Specialty</span>
                    <select value={specialty} onChange={(e) => setSpecialty(e.target.value)}>
                      {(specialties.length ? specialties : [{ id: "gp", name: "General Physician" }]).map((s) => (
                        <option key={s.id} value={s.name}>{s.name}</option>
                      ))}
                    </select>
                  </label>
                  <label className="auth-field plain">
                    <span>Years of Experience</span>
                    <input type="number" min={0} max={50} value={experienceYears} onChange={(e) => setExperienceYears(e.target.value)} required />
                  </label>
                </div>
              )}

              {registerStep === 3 && registerRole === "patient" && (
                <div className="auth-step-panel">
                  <div className="auth-info-banner">
                    <span className="material-symbols-outlined">info</span>
                    <p>This information helps personalize educational guidance and your dashboard. You can skip optional fields and add them later.</p>
                  </div>
                  <label className="auth-field plain">
                    <span>Known Allergies <em>(Optional)</em></span>
                    <textarea value={allergies} onChange={(e) => setAllergies(e.target.value)} rows={3} placeholder="e.g. Penicillin, Peanuts, Latex..." />
                  </label>
                  <label className="auth-field plain">
                    <span>Chronic Conditions <em>(Optional)</em></span>
                    <textarea value={conditions} onChange={(e) => setConditions(e.target.value)} rows={3} placeholder="e.g. Type 2 Diabetes, Hypertension..." />
                  </label>
                  <label className="auth-check">
                    <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
                    <span>I consent to MediAI processing my health information to provide educational guidance and platform features.</span>
                  </label>
                </div>
              )}

              {emailExists && (
                <EmailExistsNotice
                  onSignIn={switchToLogin}
                  onForgotPassword={switchToForgot}
                />
              )}

              {error && <p className="auth-error">{error}</p>}

              <div className="auth-form-actions">
                {registerStep > 1 ? (
                  <button
                    type="button"
                    className="auth-back-btn"
                    onClick={() => { setRegisterStep((s) => s - 1); setError(""); setEmailExists(false); }}
                  >
                    <span className="material-symbols-outlined">arrow_back</span>
                    Back
                  </button>
                ) : (
                  <span />
                )}
                <button type="submit" className="auth-next-btn" disabled={loading}>
                  {loading
                    ? "Please wait..."
                    : registerStep === totalSteps
                      ? "Create Account"
                      : "Next"}
                  <span className="material-symbols-outlined">
                    {registerStep === totalSteps ? "check_circle" : "arrow_forward"}
                  </span>
                </button>
              </div>
            </form>
          </section>
        </div>
      </main>

      <footer className="auth-register-footer">
        <span>© {new Date().getFullYear()} MediAI. Educational AI guidance — not a substitute for professional medical care.</span>
        <div className="auth-footer-links">
          <button type="button">Privacy Policy</button>
          <button type="button">Terms of Service</button>
          <button type="button">Accessibility</button>
          <button type="button">Contact</button>
        </div>
      </footer>

      {showSuccess && (
        <div className="auth-success-modal">
          <div className="auth-success-card">
            <div className="auth-success-icon">
              <span className="material-symbols-outlined">task_alt</span>
            </div>
            <h2>Welcome!</h2>
            <p>Your account has been created successfully. Redirecting to your dashboard...</p>
          </div>
        </div>
      )}
    </div>
  );
}
