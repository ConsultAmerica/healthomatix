import Image from "next/image";
import Link from "next/link";
import { BrandMark } from "./brand-mark";
import { FeatureAccordion } from "./feature-accordion";
import { FeatureTabs } from "./feature-tabs";
import { HeroStage } from "./hero-stage";
import { PageMotion } from "./page-motion";
import { ProductMock } from "./product-mocks";

const metrics = [
  { value: "2", label: "Live role previews", detail: "Clinic workspace + patient portal" },
  { value: "18+", label: "API domain objects", detail: "From ClinicRead to ConsentRead" },
  { value: "4", label: "Care connections mapped", detail: "Patients · clinics · labs · pharmacies" },
  { value: "0", label: "Live PHI exposed", detail: "Preview surfaces stay honest" },
];

const platformObjects = [
  {
    name: "ClinicRead",
    purpose: "Tenant, location, timezone, and role for an authenticated clinic session.",
    fields: ["display_name", "slug", "location_name", "timezone", "role", "tenant_id"],
  },
  {
    name: "AppointmentRead",
    purpose: "Scheduled visit bound to provider, location, patient membership, and status.",
    fields: ["starts_at", "ends_at", "provider_name", "location_name", "status", "timezone"],
  },
  {
    name: "AvailabilityRead",
    purpose: "Bookable provider slots that gate AppointmentCreate writes.",
    fields: ["starts_at", "ends_at", "provider_name", "location_id", "status"],
  },
  {
    name: "CredentialRead",
    purpose: "Provider credential lifecycle with clinic-only review decisions.",
    fields: ["credential_type", "jurisdiction", "regulator", "status", "reviewed_at"],
  },
  {
    name: "ConsentRead",
    purpose: "Purpose, scope, and policy version that trim what previews can show.",
    fields: ["purpose", "scope", "policy_version", "granted_at", "withdrawn_at"],
  },
  {
    name: "PatientProfileRead",
    purpose: "Patient identity fields—masked in preview until secure access exists.",
    fields: ["preferred_name", "date_of_birth", "phone", "locale"],
  },
  {
    name: "InvitationRead",
    purpose: "Single-use codes that join members or patients to a clinic safely.",
    fields: ["invitation_type", "expires_at", "status"],
  },
  {
    name: "DocumentRead",
    purpose: "Consent-scoped documents—never implied as live chart access here.",
    fields: ["document_type", "status", "created_at"],
  },
];

const applications = [
  {
    title: "Ground your clinic workspace",
    detail:
      "Open the clinic preview to walk ClinicRead readiness, MemberRead invites, CredentialRead review, and scheduling gates—without a live clinic account.",
    href: "/clinic",
    cta: "Open clinic preview",
    mock: "clinic-workspace" as const,
    photo: "/photos/app-clinic.jpg",
  },
  {
    title: "Connect patients with consent-aware views",
    detail:
      "Explore the patient portal structure: masked PatientProfileRead, AppointmentRead timelines, and ConsentRead scopes that stay honest about limits.",
    href: "/patient",
    cta: "Open patient preview",
    mock: "patient-portal" as const,
    photo: "/photos/app-patient.jpg",
  },
  {
    title: "Map the wider care network",
    detail:
      "Patients and clinics are live preview paths today. Laboratories and pharmacies appear on the product map as planned edges—never presented as available.",
    href: "#connections",
    cta: "View care connections",
    mock: "care-graph" as const,
    photo: "/photos/app-care.jpg",
  },
];

const stories = [
  {
    quote:
      "We needed a clinic workspace that showed readiness clearly—what the team can do now, and what still waits on secure access.",
    who: "Clinic operations lead",
    context: "Care team preview feedback",
    photo: "/photos/hero-2.jpg",
  },
  {
    quote:
      "Patients should feel informed without the portal pretending it has their full chart. Masked fields and consent scopes made that tangible.",
    who: "Patient experience designer",
    context: "Portal walkthrough",
    photo: "/photos/hero-1.jpg",
  },
];

const reasons = [
  {
    title: "Workflows grounded in real objects",
    detail:
      "Screens map to ClinicRead, AppointmentRead, CredentialRead, and ConsentRead—not generic dashboard widgets.",
  },
  {
    title: "Privacy in the payload",
    detail:
      "PatientProfileRead stays masked. DocumentRead is consent-scoped. Previews never invent live PHI.",
  },
  {
    title: "Gates you can see",
    detail:
      "Credential review, invitation codes, and availability writes are explicit states—not hidden blockers.",
  },
  {
    title: "Role-aware paths",
    detail:
      "Clinic admins, providers, and patients each get a surface that matches how they actually work.",
  },
];

const faqs = [
  {
    q: "Is this a live clinical system?",
    a: "No. This is a development preview. Secure sign-in and access to live clinic or patient data are not configured. UI mocks use sample-shaped objects (ClinicRead, AppointmentRead, ConsentRead) to show structure—not real records.",
  },
  {
    q: "What backend objects power the previews?",
    a: "The platform API defines objects such as ClinicRead, MemberRead, AvailabilityRead, AppointmentRead, CredentialRead, PatientProfileRead, ConsentRead, InvitationRead, LocationRead, and DocumentRead. Previews demonstrate how those objects surface in workflows.",
  },
  {
    q: "Who can explore the previews?",
    a: "Anyone can explore the clinic workspace and patient portal demonstrations. They show structure, readiness language, and object shapes—not live care actions.",
  },
  {
    q: "Are laboratories and pharmacies available?",
    a: "Those connections are planned. They appear in the care graph so the roadmap is clear, but InvitationRead / MembershipRead paths for labs and pharmacies are not live yet.",
  },
  {
    q: "How is privacy handled in the preview?",
    a: "Patient information stays unavailable. ConsentRead scopes, masked PatientProfileRead fields, and readiness notices make limitations obvious instead of implying live access.",
  },
];

export default function HomePage() {
  return (
    <main className="home" id="main-content" tabIndex={-1}>
      <PageMotion />
      <a className="skip-link" href="#main-content">Skip to content</a>

      <header className="site-header">
        <Link className="brand" href="/" aria-label="Healthomatix home">
          <BrandMark />
        </Link>
        <nav className="main-nav" aria-label="Main navigation">
          <a href="#overview">Overview</a>
          <a href="#features">Features</a>
          <a href="#objects">Objects</a>
          <a href="#connections">Connections</a>
          <a href="#faq">FAQ</a>
        </nav>
        <div className="header-actions">
          <Link className="text-link" href="/patient">Patient portal</Link>
          <Link className="button button-small" href="/clinic">
            Explore clinic
          </Link>
        </div>
      </header>

      <section className="hero" id="platform" aria-labelledby="home-title">
        <div className="hero-mesh" aria-hidden="true">
          <span className="mesh-blob mesh-a" />
          <span className="mesh-blob mesh-b" />
          <span className="mesh-blob mesh-c" />
        </div>
        <HeroStage />
        <div className="hero-copy">
          <p className="hero-eyebrow">Connected care platform</p>
          <h1 id="home-title" className="brand-hero">Healthomatix</h1>
          <p className="hero-lead">
            Unlock and activate care workflows across clinics and patients. Healthomatix
            connects ClinicRead workspaces, AppointmentRead schedules, CredentialRead gates,
            and ConsentRead privacy—so every role stays in sync without false live access.
          </p>
          <div className="hero-actions">
            <Link className="button" href="/clinic">
              Explore the clinic preview
            </Link>
            <Link className="button button-light" href="/patient">
              Explore the patient preview
            </Link>
          </div>
          <div className="hero-object-strip" aria-label="Featured platform objects">
            {["ClinicRead", "AppointmentRead", "CredentialRead", "ConsentRead", "PatientProfileRead"].map((name) => (
              <code key={name}>{name}</code>
            ))}
          </div>
        </div>
      </section>

      <nav className="page-rail" aria-label="On this page">
        <a href="#overview">Overview</a>
        <a href="#features">Features</a>
        <a href="#applications">Applications</a>
        <a href="#objects">Objects</a>
        <a href="#connections">Connections</a>
        <a href="#approach">Approach</a>
        <a href="#faq">FAQ</a>
      </nav>

      <section className="overview" id="overview" aria-labelledby="overview-title" data-reveal>
        <div className="section-intro section-intro-wide">
          <p className="section-kicker">Overview</p>
          <h2 id="overview-title">Build agents of care on unified clinic context</h2>
          <p>
            Point-and-click readiness for care teams, consent-aware patient views, and
            enterprise-minded privacy—reusable across roles, grounded in your platform API.
          </p>
        </div>
        <FeatureAccordion />
      </section>

      <section className="features" id="features" aria-labelledby="features-title" data-reveal>
        <div className="section-intro section-intro-wide">
          <p className="section-kicker">Features</p>
          <h2 id="features-title">Deliver relevant care responses with search across your clinic objects</h2>
          <p>
            Rotate through workspace, portal, scheduling, credentials, and consent—each panel
            backed by live-shaped API objects and interactive product surfaces.
          </p>
        </div>
        <FeatureTabs />
      </section>

      <section className="applications" id="applications" aria-labelledby="applications-title" data-reveal>
        <div className="section-intro">
          <p className="section-kicker">Applications</p>
          <h2 id="applications-title">Explore common applications to get started</h2>
          <p>
            Pick a path that matches your role. Each card opens a demonstration surface—structure
            and intent only, never live patient information.
          </p>
        </div>
        <div className="application-showcase">
          {applications.map((app) => (
            <article className="application-showcase-card" key={app.title} data-reveal>
              <div className="application-showcase-visual" aria-hidden="true">
                <div className="application-photo">
                  <Image src={app.photo} alt="" fill sizes="(max-width: 900px) 100vw, 55vw" />
                </div>
                <div className="application-mock-overlay">
                  <ProductMock kind={app.mock} />
                </div>
              </div>
              <div className="application-showcase-copy">
                <h3>{app.title}</h3>
                <p>{app.detail}</p>
                <Link className="text-arrow-link" href={app.href}>
                  {app.cta} <span aria-hidden="true">→</span>
                </Link>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="objects" id="objects" aria-labelledby="objects-title" data-reveal>
        <div className="section-intro">
          <p className="section-kicker">Platform objects</p>
          <h2 id="objects-title">Backend objects that power every preview</h2>
          <p>
            These schemas come from the Healthomatix API. Landing mocks and portal screens
            speak the same language—so product, design, and engineering stay aligned.
          </p>
        </div>
        <div className="object-grid">
          {platformObjects.map((object, index) => (
            <article
              className="object-card"
              key={object.name}
              data-reveal
              style={{ transitionDelay: `${Math.min(index, 7) * 40}ms` }}
            >
              <header>
                <code>{object.name}</code>
                <span>schema</span>
              </header>
              <p>{object.purpose}</p>
              <ul>
                {object.fields.map((field) => (
                  <li key={field}>{field}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </section>

      <section className="trust" aria-labelledby="trust-title" data-reveal>
        <h2 id="trust-title" className="visually-hidden">Preview foundations</h2>
        <div className="metric-grid">
          {metrics.map((metric) => (
            <article key={metric.label}>
              <strong>{metric.value}</strong>
              <span>{metric.label}</span>
              <small>{metric.detail}</small>
            </article>
          ))}
        </div>
      </section>

      <section className="stories" aria-labelledby="stories-title" data-reveal>
        <div className="section-intro">
          <p className="section-kicker">Stories</p>
          <h2 id="stories-title">What early walkthroughs are teaching us</h2>
        </div>
        <div className="story-grid">
          {stories.map((story) => (
            <blockquote className="story-card" key={story.who}>
              <div className="story-photo" aria-hidden="true">
                <Image src={story.photo} alt="" fill sizes="(max-width: 900px) 100vw, 40vw" />
              </div>
              <div className="story-copy">
                <p>“{story.quote}”</p>
                <footer>
                  <strong>{story.who}</strong>
                  <span>{story.context}</span>
                </footer>
              </div>
            </blockquote>
          ))}
        </div>
      </section>

      <section className="connections" id="connections" aria-labelledby="connections-title" data-reveal>
        <div className="connections-heading">
          <div>
            <p className="section-kicker">Connections</p>
            <h2 id="connections-title">Made for everyone in the care journey</h2>
          </div>
          <p>
            Start with patient and clinic MembershipRead paths. Laboratory and pharmacy edges
            are mapped for the future—visible on the graph, not available as live previews.
          </p>
        </div>
        <div className="connections-layout">
          <div className="connections-visual" aria-hidden="true">
            <ProductMock kind="care-graph" />
          </div>
          <div className="role-grid">
            {[
              { label: "Patients", detail: "PatientProfileRead + AppointmentRead portal.", tone: "solid" },
              { label: "Care teams", detail: "ClinicRead workspace with readiness gates.", tone: "solid-alt" },
              { label: "Laboratories", detail: "Future edge on the care graph.", tone: "soft", status: "Planned" },
              { label: "Pharmacies", detail: "Future edge on the care graph.", tone: "soft", status: "Planned" },
            ].map((role, index) => (
              <article className={`role-card role-${role.tone}`} key={role.label}>
                <div className="role-card-top">
                  <span className="role-number">0{index + 1}</span>
                  {"status" in role && role.status ? (
                    <span className="coming-soon">{role.status}</span>
                  ) : null}
                </div>
                <div className="role-card-copy">
                  <h3>{role.label}</h3>
                  <p>{role.detail}</p>
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="why" id="approach" aria-labelledby="why-title" data-reveal>
        <div className="section-intro">
          <p className="section-kicker">Approach</p>
          <h2 id="why-title">Why this approach to connected care</h2>
          <p>
            User-centered product decisions grounded in API reality—keeping clinics productive
            and patients confident without overselling what the preview can do.
          </p>
        </div>
        <div className="why-grid">
          {reasons.map((reason) => (
            <article className="why-card" key={reason.title}>
              <h3>{reason.title}</h3>
              <p>{reason.detail}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="portal-callout" aria-labelledby="starting-point-title">
        <div>
          <p className="section-kicker">Get started</p>
          <h2 id="starting-point-title">Explore a preview for your role</h2>
          <p className="callout-description">
            These screens are demonstrations only. Secure sign-in and access to live clinic data
            are not available. Object mocks illustrate shape—not production records.
          </p>
        </div>
        <div className="callout-actions">
          <Link className="callout-link" href="/clinic">
            <span className="callout-symbol" aria-hidden="true">✚</span>
            <span>
              <strong>Clinic workspace</strong>
              <small>ClinicRead · CredentialRead · AvailabilityRead</small>
            </span>
            <span className="callout-arrow" aria-hidden="true">→</span>
          </Link>
          <Link className="callout-link" href="/patient">
            <span className="callout-symbol patient-symbol" aria-hidden="true">♡</span>
            <span>
              <strong>Patient portal</strong>
              <small>PatientProfileRead · AppointmentRead · ConsentRead</small>
            </span>
            <span className="callout-arrow" aria-hidden="true">→</span>
          </Link>
        </div>
      </section>

      <section className="faq" id="faq" aria-labelledby="faq-title">
        <div className="section-intro">
          <p className="section-kicker">FAQ</p>
          <h2 id="faq-title">Frequently asked questions</h2>
          <p>Clear answers about objects, previews, and what is—and is not—live.</p>
        </div>
        <div className="faq-list">
          {faqs.map((item, index) => (
            <details className="faq-item" key={item.q}>
              <summary>
                <span className="faq-index">{String(index + 1).padStart(2, "0")}</span>
                {item.q}
              </summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <footer className="site-footer">
        <Link className="brand brand-footer" href="/">
          <BrandMark />
        </Link>
        <p>Care connections, thoughtfully designed.</p>
        <span className="preview-disclaimer">Development preview · No live patient information</span>
      </footer>
    </main>
  );
}
