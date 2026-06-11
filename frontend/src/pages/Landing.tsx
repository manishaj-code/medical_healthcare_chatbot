import { useState } from "react";
import { Link } from "react-router-dom";
import GuestChatWidget from "../components/GuestChatWidget";

export default function Landing() {
  const [chatOpen, setChatOpen] = useState(true);

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
                AI Health Assistant Platform
              </span>
              <h1>Understand Your Health, With Clear AI Guidance</h1>
              <p>
                MediAI helps you explore symptoms, understand lab reports, and book care—in plain
                language, available anytime. Built with multi-agent AI and secure patient workflows.
              </p>
              <div className="landing-hero-cta">
                <button type="button" className="landing-btn-primary" onClick={openChat}>
                  Start AI Consultation
                  <span className="material-symbols-outlined">arrow_forward</span>
                </button>
                <a href="#features" className="landing-btn-outline">Explore Features</a>
              </div>
              <p className="landing-hero-note">
                Not a substitute for professional medical advice, diagnosis, or emergency care.
              </p>
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
                  <span className="material-symbols-outlined">smart_toy</span>
                  <div>
                    <strong>Multi-Agent AI</strong>
                    <small>Triage · Reports · Booking</small>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="landing-features" id="features">
          <div className="landing-container">
            <div className="landing-section-head">
              <h2>Intelligent Health Support</h2>
              <p>
                Modern LLM-powered agents work together to help you navigate symptoms, documents,
                and appointments—with responses grounded in your conversation and uploaded reports.
              </p>
            </div>
            <div className="landing-feature-grid">
              {[
                {
                  icon: "stethoscope",
                  title: "Symptom Triage",
                  text: "Describe how you feel and get guided follow-up questions, specialty suggestions, and next-step options.",
                },
                {
                  icon: "medication",
                  title: "Health Education",
                  text: "Ask about conditions, medications, and wellness topics in clear, patient-friendly language.",
                },
                {
                  icon: "lab_research",
                  title: "Lab Report Analysis",
                  text: "Upload PDFs, images, spreadsheets, or text files and receive an educational summary of your results.",
                },
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
              <h2>Built for Real Patient Workflows</h2>
              <ul className="landing-check-list">
                <li>
                  <span className="material-symbols-outlined">check_circle</span>
                  <div>
                    <strong>Context-Aware Chat</strong>
                    <p>Remembers your session so triage, reports, and booking stay connected.</p>
                  </div>
                </li>
                <li>
                  <span className="material-symbols-outlined">lock</span>
                  <div>
                    <strong>Privacy-Focused Access</strong>
                    <p>Sign in or verify your email when you need appointments, uploads, and your dashboard.</p>
                  </div>
                </li>
                <li>
                  <span className="material-symbols-outlined">clinical_notes</span>
                  <div>
                    <strong>Care Team Ready</strong>
                    <p>Generate visit summaries and keep reports organized for discussions with your clinician.</p>
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
                    Hello! I&apos;m your MediAI Assistant. How are you feeling today?
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
              ["24/7", "AI Consultation"],
              ["Multi-Agent", "Specialist Routing"],
              ["Reports", "PDF · Image · Excel"],
              ["Secure", "Patient Accounts"],
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
            <h2>Ready to Explore Smarter Health Guidance?</h2>
            <p>
              Start with guest chat at no cost. Create an account when you want appointments,
              report uploads, and your personal health dashboard.
            </p>
            <div className="landing-hero-cta landing-hero-cta--center">
              <button type="button" className="landing-btn-primary" onClick={openChat}>
                Get Started Free
              </button>
              <Link to="/login" className="landing-btn-secondary">Sign In</Link>
            </div>
            <small>Educational AI guidance only · Always consult a licensed clinician for medical decisions</small>
          </div>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="landing-container landing-footer-grid">
          <div>
            <strong className="landing-logo">MediAI</strong>
            <p>© {new Date().getFullYear()} MediAI. AI-assisted health guidance for patients and care teams.</p>
            <p className="landing-footer-disclaimer">
              MediAI provides educational information and workflow support. It does not provide medical
              diagnosis, treatment, or emergency services. Call your local emergency number for urgent care.
            </p>
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
