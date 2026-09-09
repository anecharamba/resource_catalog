export default function Privacy() {
  return (
    <div className="legal-page">
      <h1 className="page-title">Privacy Policy</h1>
      <p className="muted legal-updated">Last updated: [add date when you publish this]</p>

      <p className="legal-notice">
        This is a starting template, not legal advice — review it (ideally with a lawyer) before
        relying on it, and fill in the bracketed placeholders with your real details.
      </p>

      <section>
        <h2>What this page covers</h2>
        <p>
          This policy explains what information ExamVault collects, how it's used, and what's
          stored on your device when you use the site — as either a student browsing papers or
          an administrator managing the catalog.
        </p>
      </section>

      <section>
        <h2>Information we collect</h2>
        <h3>If you're browsing or downloading papers</h3>
        <p>
          Browsing and searching the catalog doesn't require an account and we don't collect
          personal information to do it. When you download a paper, we record that a download
          happened (to power the "Most downloaded" list) but not who downloaded it — no name,
          email, or IP address is tied to that count.
        </p>
        <h3>If you're an administrator</h3>
        <p>
          Admin accounts store a username and a password. Passwords are hashed (bcrypt) before
          storage — we never store or can retrieve your actual password. We also log which admin
          account started each import batch, for accountability within the team.
        </p>
      </section>

      <section>
        <h2>Cookies and similar technologies</h2>
        <p>
          ExamVault does not use tracking or advertising cookies, and doesn't share data with
          ad networks or analytics providers. What we do use is your browser's local storage
          (not a cookie, but a similar on-device technology) for two things:
        </p>
        <ul>
          <li><strong>Theme preference</strong> — remembers whether you chose light or dark mode.</li>
          <li><strong>Admin session</strong> — if you're an admin, a login token is kept in local
            storage so you don't have to sign in on every page load. This never leaves your
            device except when sent to our own server to verify your session.</li>
        </ul>
        <p>
          Both are essential to the site functioning as intended, not used for tracking, and
          never sold or shared with third parties. You can clear them at any time by clearing
          your browser's site data, which will reset your theme and sign you out if you're an
          admin.
        </p>
      </section>

      <section>
        <h2>How we use information</h2>
        <ul>
          <li>To operate the search, browse, and download features of the catalog</li>
          <li>To authenticate administrators and control who can manage the catalog</li>
          <li>To improve the catalog over time (e.g. surfacing popular or recently added papers)</li>
        </ul>
        <p>We don't use any information to build advertising profiles, and we don't sell data.</p>
      </section>

      <section>
        <h2>Third parties</h2>
        <p>
          [Fill in: list anything that actually applies once deployed — e.g. your hosting
          provider, database provider, or file storage provider, since they process data on your
          behalf even though they don't see it for their own purposes. As of this template, the
          site has no third-party analytics, ads, or trackers.]
        </p>
      </section>

      <section>
        <h2>Data retention</h2>
        <p>
          Catalog metadata and download counts are kept indefinitely as part of the archive.
          Admin accounts persist until removed by another administrator. [Fill in: add a real
          retention/deletion policy once you decide one — e.g. how long you keep server logs.]
        </p>
      </section>

      <section>
        <h2>Children's privacy</h2>
        <p>
          The student-facing side of ExamVault doesn't collect personal information, so it can
          be used without providing any personal data, including by students under 18. Admin
          accounts are intended for staff, not students.
        </p>
      </section>

      <section>
        <h2>Security</h2>
        <p>
          Admin passwords are hashed, not stored in plain text. Admin sessions expire
          automatically after 12 hours. [Fill in: describe any additional measures once deployed,
          e.g. HTTPS enforcement, hosting provider security practices.]
        </p>
      </section>

      <section>
        <h2>Changes to this policy</h2>
        <p>
          If this policy changes in a way that affects what we collect or how it's used, we'll
          update the date at the top of this page.
        </p>
      </section>

      <section>
        <h2>Contact</h2>
        <p>
          Questions about this policy or your data: [add a real contact email here].
        </p>
      </section>
    </div>
  );
}
