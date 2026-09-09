import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <span className="muted">© {new Date().getFullYear()} ExamVault</span>
        <Link to="/privacy" className="link">Privacy Policy</Link>
      </div>
    </footer>
  );
}
