import { useState } from "react";
import { Link } from "react-router-dom";
import GuestChatWidget from "../components/GuestChatWidget";

export default function Landing() {
  const [chatOpen, setChatOpen] = useState(false);

  const openChat = () => setChatOpen(true);

  return (
    <div className="landing-page">
      <nav className="landing-nav">
        <Link to="/" className="landing-logo">MediAI</Link>
        <div className="landing-nav-links">
          <a href="#features">Features</a>
          <a href="#about">About</a>
          <Link to="/login" className="landing-signin">Sign In</Link>
        </div>
      </nav>

      <main>
        <section className="landing-hero">
          <div className="landing-container landing-hero-grid">
            <div className="landing-hero-copy">
              <span className="landing-badge">
                <span className="landing-badge-dot" />
                Clinical Intelligence v2.4 Now Live
              </span>
              <h1>Your Health, Answered by Intelligence</h1>
              <p>
                Experience 24/7 access to clinical insights. MediAI bridges the gap between medical
                complexity and personal understanding with our HIPAA-compliant medical chat engine.
              </p>
              <div className="landing-hero-cta">
                <button type="button" className="landing-btn-primary" onClick={openChat}>
                  Start AI Consultation
                  <span className="material-symbols-outlined">arrow_forward</span>
                </button>
                <a href="#features" className="landing-btn-outline">View Clinical Standards</a>
              </div>
            </div>
            <div className="landing-hero-visual">
              <div className="landing-hero-glow" aria-hidden="true" />
              <div className="landing-hero-card">
                <img
                  className="landing-hero-mock"
                  src="/images/landing-hero-phone.png"
                  alt="MediAI mobile assistant showing symptom chat on a smartphone"
                />
                <div className="landing-hero-stat">
                  <span className="material-symbols-outlined">verified</span>
                  <div>
                    <strong>99.2% Accuracy</strong>
                    <small>Clinical Benchmark</small>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-features" id="features">
          <div className="landing-container">
            <div className="landing-section-head">
              <h2>Precision-Engineered Support</h2>
              <p>
                Our intelligence engine is trained on millions of peer-reviewed clinical documents to
                provide you with the most accurate health context possible.
              </p>
            </div>
            <div className="landing-feature-grid">
              {[
                { icon: "stethoscope", title: "Symptom Analysis", text: "Interactive triage questions designed by board-certified physicians." },
                { icon: "medication", title: "Medication Insights", text: "Understand drug interactions and side effects in plain language." },
                { icon: "lab_research", title: "Lab Explanations", text: "Upload test results and get an easy-to-read breakdown of your markers." },
              ].map((f) => (
                <article key={f.title} className="landing-feature-card">
                  <div className="landing-feature-icon">
                    <span className="material-symbols-outlined">{f.icon}</span>
                  </div>
                  <h3>{f.title}</h3>
                  <p>{f.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="landing-chat-section" id="about">
          <div className="landing-container landing-chat-section-grid">
            <div>
              <h2>Experience the Chat Interface</h2>
              <ul className="landing-check-list">
                <li>
                  <span className="material-symbols-outlined">check_circle</span>
                  <div>
                    <strong>Context-Aware AI</strong>
                    <p>Remembers symptoms within your session for a holistic view.</p>
                  </div>
                </li>
                <li>
                  <span className="material-symbols-outlined">lock</span>
                  <div>
                    <strong>Secure by Design</strong>
                    <p>Verify your email only when you need booking and dashboard access.</p>
                  </div>
                </li>
                <li>
                  <span className="material-symbols-outlined">clinical_notes</span>
                  <div>
                    <strong>Physician Export</strong>
                    <p>Generate summaries for your primary care provider after sign-up.</p>
                  </div>
                </li>
              </ul>
            </div>
            <div className="landing-chat-demo">
              <div className="landing-chat-demo-window">
                <div className="landing-chat-demo-head">
                  <span>MediAI Assistant</span>
                  <span className="material-symbols-outlined">smart_toy</span>
                </div>
                <div className="landing-chat-demo-body">
                  <div className="landing-chat-demo-bubble landing-chat-demo-bubble--ai">
                    Hello! I&apos;m your MediAI assistant. How are you feeling today?
                  </div>
                  <div className="landing-chat-demo-bubble landing-chat-demo-bubble--user">
                    I&apos;ve had a persistent headache for two days and I&apos;m feeling a bit dizzy.
                  </div>
                  <div className="landing-chat-demo-bubble landing-chat-demo-bubble--ai">
                    I understand. To help me narrow this down, are you experiencing any light
                    sensitivity or nausea? Also, have you been staying hydrated?
                    <div className="landing-chat-demo-chips">
                      <span>Yes, nausea</span>
                      <span>Light sensitivity</span>
                      <span>Neither</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-stats">
          <div className="landing-container landing-stats-grid">
            {[
              ["5M+", "Consultations"],
              ["12k+", "Clinicians Trusted"],
              ["15s", "Avg. Response Time"],
              ["4.9/5", "Patient Rating"],
            ].map(([n, l]) => (
              <div key={l}>
                <strong>{n}</strong>
                <span>{l}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="landing-cta">
          <div className="landing-container landing-cta-inner">
            <h2>Ready for Smarter Health Insights?</h2>
            <p>Start chatting free — verify your email only when you need appointments and advanced tools.</p>
            <div className="landing-hero-cta landing-hero-cta--center">
              <button type="button" className="landing-btn-primary" onClick={openChat}>
                Get Started Free
              </button>
              <Link to="/login" className="landing-btn-secondary">Sign In</Link>
            </div>
            <small>No credit card required · Secure data processing</small>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="landing-container landing-footer-grid">
          <div>
            <strong className="landing-logo">MediAI</strong>
            <p>© {new Date().getFullYear()} MediAI. Professional health insights powered by clinical intelligence.</p>
          </div>
          <div>
            <h5>Product</h5>
            <a href="#features">Features</a>
            <a href="#about">About</a>
          </div>
          <div>
            <h5>Resources</h5>
            <a href="#about">Medical Disclaimer</a>
            <a href="#about">Privacy Policy</a>
          </div>
          <div>
            <h5>Support</h5>
            <Link to="/login">Sign In</Link>
          </div>
        </div>
      </footer>

      <GuestChatWidget open={chatOpen} onOpenChange={setChatOpen} />
    </div>
  );
}
