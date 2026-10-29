import Image from "next/image";
import Link from "next/link";
import { CareGraphExplorer } from "@/components/landing/care-graph-explorer";
import { ConsentScopePreview } from "@/components/landing/consent-scope-preview";
import { SchemaInspector } from "@/components/landing/schema-inspector";
import { ThemeToggle } from "@/components/theme-provider";
import { BrandMark } from "./brand-mark";
import { FeatureAccordion } from "./feature-accordion";
import { FeatureTabs } from "./feature-tabs";
import { HeroStage } from "./hero-stage";
import { PageMotion } from "./page-motion";
import { ProductMock } from "./product-mocks";

const metrics = [
  { value: "3", label: "Connected portals", detail: "Clinic admin · provider · patient" },
  { value: "1", label: "AI document path", detail: "Upload → extract → verify → timeline" },
  { value: "Multi-tenant", label: "Clinic isolation", detail: "Role-based access + audit trail" },
  { value: "0", label: "Live PHI exposed", detail: "Synthetic demos stay honest" },
];

const platformObjects = [
  {
    name: "ClinicRead",
    label: "Clinic Information",
    purpose: "Tenant, location, timezone, and role for an authenticated clinic session.",
    fields: ["display_name", "slug", "location_name", "timezone", "role", "tenant_id"],
  },
  {
    name: "AppointmentRead",
    label: "Appointments",
    purpose: "Scheduled visit bound to provider, location, patient membership, and status.",
    fields: ["starts_at", "ends_at", "provider_name", "location_name", "status", "timezone"],
  },
  {
    name: "AvailabilityRead",
    label: "Availability",
    purpose: "Bookable provider slots that gate appointment booking.",
    fields: ["starts_at", "ends_at", "provider_name", "location_id", "status"],
  },
  {
    name: "CredentialRead",
    label: "Provider Credentials",
    purpose: "Provider credential lifecycle with clinic-only review decisions.",
    fields: ["credential_type", "jurisdiction", "regulator", "status", "reviewed_at"],
  },
  {
    name: "ConsentRead",
    label: "Patient Consent",
    purpose: "Purpose, scope, and policy version that trim what care teams can see.",
    fields: ["purpose", "scope", "policy_version", "granted_at", "withdrawn_at"],
  },
  {
    name: "PatientProfileRead",
    label: "Patient Profile",
    purpose: "Patient identity fields—masked in preview until secure access exists.",
    fields: ["preferred_name", "date_of_birth", "phone", "locale"],
  },
  {
    name: "InvitationRead",
    label: "Invitations",
    purpose: "Single-use codes that join members or patients to a clinic safely.",
    fields: ["invitation_type", "expires_at", "status"],
  },
  {
    name: "DocumentRead",
    label: "Medical Records",
    purpose: "Consent-scoped documents—never implied as live chart access here.",
    fields: ["document_type", "status", "created_at"],
  },
];

const applications = [
  {
    title: "Clinic & clinician workspace",
    detail:
      "Invite your team, verify credentials, review today’s visits, approve AI drafts, and keep every clinic’s records isolated.",
    href: "/clinic",
    cta: "Explore clinic demo",
    mock: "clinic-workspace" as const,
    photo: "/photos/app-clinic.jpg",
  },
  {
    title: "Patient portal",
    detail:
      "Book care, upload lab reports, follow a Health Timeline, and control consent scopes that trim what the clinic can see.",
    href: "/patient",
    cta: "Explore patient demo",
    mock: "patient-portal" as const,
    photo: "/photos/app-patient.jpg",
  },
  {
    title: "Consultations & AI documentation",
    detail:
      "Move from booking into a visit workspace with source-linked summaries and clinician-approved notes—AI assists, clinicians decide.",
    href: "/clinic/consultations",
    cta: "Open consultation workspace",
    mock: "scheduling" as const,
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
    title: "Built for clinic operations",
    detail:
      "Appointments, credentials, chart access, and consult documentation share one tenant-aware workflow—not disconnected tools.",
  },
  {
    title: "AI inside the workflow",
    detail:
      "Document extraction, trends, and draft notes appear where clinicians already work, with mandatory human review before anything is signed.",
  },
  {
    title: "Privacy you can demonstrate",
    detail:
      "Consent scopes, audit events, and masked previews make authorization visible—without claiming HIPAA certification.",
  },
  {
    title: "Role-specific portals",
    detail:
      "Clinic administrators, providers, and patients each get navigation and dashboards matched to their job—not one generic screen.",
  },
];

const faqs = [
  {
    q: "Is Healthomatix a live clinical system today?",
    a: "This deployment is a synthetic demonstration and development preview. Demo accounts use masked or sample data. Do not enter real patient information, and do not treat the product as HIPAA-certified.",
  },
  {
    q: "Who is Healthomatix for?",
    a: "Clinics, clinicians, and patients who need connected scheduling, records, consultations, documentation, and AI-assisted workflows in one multi-tenant platform.",
  },
  {
    q: "How do I request a demo?",
    a: "Open the clinic workspace, sign in with a demo account (or your configured identity provider), and use Seed sandbox to provision a shared clinic linking admin, provider, and patient personas.",
  },
  {
    q: "What AI capabilities are available in the demo?",
    a: "Document upload with Fake OCR extraction, clinician verification into Observations, Health Timeline and trends, plus clinician-approved visit summaries, notes, and follow-up tasks.",
  },
  {
    q: "Are laboratories and pharmacies connected?",
    a: "They appear on the care network map as planned edges with target standards (HL7/FHIR, NCPDP). Patient and clinic membership paths are available in the demo today.",
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
          <a href="#features">Features</a>
          <a href="#applications">Product</a>
          <a href="#demo">Demo</a>
          <a href="#connections">Network</a>
          <a href="#faq">FAQ</a>
        </nav>
        <div className="header-actions">
          <ThemeToggle compact />
          <Link className="text-link" href="/patient">
            Explore Patient Demo
          </Link>
          <Link className="button button-small" href="/clinic">
            Explore Clinic Demo
          </Link>
        </div>
      </header>

      <section className="hero" id="platform" aria-labelledby="home-title">
        <div className="hero-mesh" aria-hidden="true">
          <span className="mesh-blob mesh-a" />
          <span className="mesh-blob mesh-b" />
          <span className="mesh-blob mesh-c" />
        </div>
        <div className="hero-copy">
          <p className="hero-eyebrow">Healthomatix · Clinic SaaS</p>
          <h1 id="home-title" className="brand-hero">One Intelligent Platform for Modern Healthcare</h1>
          <p className="hero-lead">
            Healthomatix connects clinics, doctors, and patients through smarter scheduling, secure
            medical records, online consultations, and AI-assisted clinical workflows.
          </p>
          <div className="hero-actions">
            <Link className="button" href="/clinic">
              Explore Clinic Demo
            </Link>
            <Link className="button button-light" href="/patient">
              Explore Patient Demo
            </Link>
          </div>
        </div>
        <HeroStage />
      </section>

      <section className="product-screen-strip" aria-label="Product surfaces" data-reveal>
        <div className="product-screen-grid">
          <figure>
            <ProductMock kind="clinic-workspace" />
            <figcaption>Clinician dashboard</figcaption>
          </figure>
          <figure>
            <ProductMock kind="patient-portal" />
            <figcaption>Patient portal</figcaption>
          </figure>
          <figure>
            <ProductMock kind="scheduling" />
            <figcaption>Consultation &amp; scheduling</figcaption>
          </figure>
        </div>
      </section>

      <nav className="page-rail" aria-label="On this page">
        <a href="#features">Features</a>
        <a href="#applications">Product</a>
        <a href="#demo">Demo</a>
        <a href="#objects">Schemas</a>
        <a href="#connections">Network</a>
        <a href="#faq">FAQ</a>
      </nav>

      <section className="overview" id="overview" aria-labelledby="overview-title" data-reveal>
        <div className="section-intro section-intro-wide">
          <p className="section-kicker">Platform</p>
          <h2 id="overview-title">One platform for clinics, clinicians, and patients</h2>
          <p>
            Replace fragmented scheduling, charting, and messaging tools with a multi-tenant
            workspace where AI assists inside clinical workflows—and clinicians stay accountable.
          </p>
        </div>
        <FeatureAccordion />
      </section>

      <section className="features" id="features" aria-labelledby="features-title" data-reveal>
        <div className="section-intro section-intro-wide">
          <p className="section-kicker">Features</p>
          <h2 id="features-title">Clinical workflows with AI where it earns its place</h2>
          <p>
            Scheduling, credentials, consent, document intelligence, telehealth visits, and
            approved documentation—connected end to end for modern care teams.
          </p>
        </div>
        <FeatureTabs />
      </section>

      <section className="applications" id="applications" aria-labelledby="applications-title" data-reveal>
        <div className="section-intro">
          <p className="section-kicker">Product</p>
          <h2 id="applications-title">Realistic screens for every role</h2>
          <p>
            Walk the clinic workspace, patient portal, and consultation path with synthetic data.
            No live PHI—just the workflows buyers need to evaluate.
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
          <p className="section-kicker">For developers</p>
          <h2 id="objects-title">API schemas behind the product</h2>
          <p>
            Everyday product language above—API contract names here. Switch JSON or TypeScript, then
            toggle consent scopes on consent-sensitive schemas to watch the sample payload change live.
          </p>
        </div>
        <SchemaInspector objects={platformObjects} />
      </section>

      <section className="consent-preview-section" id="consent-preview" aria-labelledby="consent-preview-title" data-reveal>
        <div className="section-intro">
          <p className="section-kicker">Privacy</p>
          <h2 id="consent-preview-title">Granular patient consent scopes</h2>
          <p>
            Toggle visit summaries, lab histories, and schedule access, then flip JSON / TypeScript to
            see how restricted scopes drop out of the payload—privacy enforced in the resource, not only
            in the UI.
          </p>
        </div>
        <ConsentScopePreview />
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
            <p className="section-kicker">Network</p>
            <h2 id="connections-title">Made for everyone in the care journey</h2>
          </div>
          <p>
            Start with patient and clinic membership paths. Laboratory and pharmacy connections
            are mapped for the future—visible on the graph, not available as live previews.
          </p>
        </div>
        <CareGraphExplorer />
      </section>

      <section className="why" id="approach" aria-labelledby="why-title" data-reveal>
        <div className="section-intro">
          <p className="section-kicker">Principles</p>
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

      <section className="portal-callout" id="demo" aria-labelledby="starting-point-title">
        <div>
          <p className="section-kicker">Request a demo</p>
          <h2 id="starting-point-title">See the connected care path in minutes</h2>
          <p className="callout-description">
            Sign in with a demo account, seed the sandbox clinic, then walk upload → AI extract →
            verify → Health Timeline → consult drafts. Synthetic data only—never enter real patient information.
          </p>
        </div>
        <div className="callout-actions">
          <Link className="callout-link" href="/clinic">
            <span className="callout-symbol" aria-hidden="true">✚</span>
            <span>
              <strong>Explore clinic demo</strong>
              <small>Admin · doctor · workboard · audit</small>
            </span>
            <span className="callout-arrow" aria-hidden="true">→</span>
          </Link>
          <Link className="callout-link" href="/patient">
            <span className="callout-symbol patient-symbol" aria-hidden="true">♡</span>
            <span>
              <strong>Explore patient demo</strong>
              <small>Timeline · records · consent · booking</small>
            </span>
            <span className="callout-arrow" aria-hidden="true">→</span>
          </Link>
          <a className="callout-link" href="mailto:hello@healthomatix.com?subject=Healthomatix%20demo%20request">
            <span className="callout-symbol" aria-hidden="true">✉</span>
            <span>
              <strong>Request a demo</strong>
              <small>Talk with our team about your clinic</small>
            </span>
            <span className="callout-arrow" aria-hidden="true">→</span>
          </a>
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

      <footer className="site-footer site-footer-modern">
        <div className="footer-brand">
          <Link className="brand brand-footer" href="/">
            <BrandMark />
          </Link>
          <p>One intelligent platform for clinics, doctors, and patients.</p>
        </div>
        <nav className="footer-nav" aria-label="Footer">
          <a href="#features">Features</a>
          <a href="#applications">Product</a>
          <a href="#demo">Demo</a>
          <a href="#faq">FAQ</a>
          <Link href="/clinic">Clinic demo</Link>
          <Link href="/patient">Patient demo</Link>
        </nav>
        <span className="preview-disclaimer">
          Synthetic demonstration · No live patient information · Not a HIPAA compliance claim
        </span>
      </footer>
    </main>
  );
}
