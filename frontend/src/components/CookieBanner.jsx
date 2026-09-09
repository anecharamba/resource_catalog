import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const STORAGE_KEY = "cookie_consent_ack";

export default function CookieBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (!window.localStorage.getItem(STORAGE_KEY)) {
        setVisible(true);
      }
    } catch {
      // localStorage unavailable (e.g. private browsing in some browsers) —
      // just don't show the banner rather than error.
    }
  }, []);

  const dismiss = () => {
    setVisible(false);
    try {
      window.localStorage.setItem(STORAGE_KEY, "1");
    } catch {
      // if storage isn't available the banner will just reappear next visit,
      // which is an acceptable fallback rather than a hard failure
    }
  };

  if (!visible) return null;

  return (
    <div className="cookie-banner" role="dialog" aria-label="Cookie and local storage notice">
      <p>
        ExamVault uses local storage for essential functionality only — remembering your theme
        preference and, for admins, your login session. No tracking or advertising cookies.{" "}
        <Link to="/privacy" className="link">Learn more</Link>
      </p>
      <button className="btn btn-primary btn-sm" onClick={dismiss}>Got it</button>
    </div>
  );
}
