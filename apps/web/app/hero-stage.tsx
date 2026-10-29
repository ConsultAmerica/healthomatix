"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

const scenes = [
  {
    src: "/photos/hero-1.jpg",
    alt: "Clinician reviewing care details with a patient",
    tone: "teal",
    cards: [
      { id: "clinic", label: "Clinic Information", value: "Northside Family Care", meta: "location · timezone", spot: "clinic" },
      { id: "appt", label: "Appointments", value: "Thu 10:30 · Dr. Patel", meta: "status: scheduled", spot: "appt" },
      { id: "consent", label: "Patient Consent", value: "visit summary shared", meta: "policy v2.1 · granted", spot: "consent" },
    ],
  },
  {
    src: "/photos/hero-2.jpg",
    alt: "Care professional in a bright modern clinic",
    tone: "blue",
    cards: [
      { id: "ready", label: "Clinic readiness", value: "3 gates open", meta: "onboarding · team · schedule", spot: "clinic" },
      { id: "cred", label: "Provider Credentials", value: "2 pending review", meta: "clinic reviewer only", spot: "appt" },
      { id: "member", label: "Care team", value: "12 seats active", meta: "secure invite codes ready", spot: "consent" },
    ],
  },
  {
    src: "/photos/hero-3.jpg",
    alt: "Modern hospital corridor with natural light",
    tone: "cyan",
    cards: [
      { id: "space", label: "Locations", value: "Main Street Clinic", meta: "timezone-aware rooms", spot: "clinic" },
      { id: "avail", label: "Availability", value: "8 open slots today", meta: "provider-bound", spot: "appt" },
      { id: "invite", label: "Invitations", value: "single-use join codes", meta: "secure outside channel", spot: "consent" },
    ],
  },
  {
    src: "/photos/hero-4.jpg",
    alt: "Hands-on clinical care in a calm setting",
    tone: "mint",
    cards: [
      { id: "patient", label: "Patient Profile", value: "•••••• · masked", meta: "sign-in required", spot: "clinic" },
      { id: "visit", label: "Appointments", value: "Next visit · Mon 14:00", meta: "timezone-aware", spot: "appt" },
      { id: "scope", label: "Patient Consent", value: "care coordination", meta: "scope trimmed at query time", spot: "consent" },
    ],
  },
];

export function HeroStage() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const [ready, setReady] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready || paused) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => {
      setIndex((current) => (current + 1) % scenes.length);
    }, 5800);
    return () => window.clearInterval(id);
  }, [paused, ready]);

  useEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    function onMove(event: MouseEvent) {
      if (!stage) return;
      const rect = stage.getBoundingClientRect();
      const x = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
      const y = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
      stage.style.setProperty("--parallax-x", `${x * 18}px`);
      stage.style.setProperty("--parallax-y", `${y * 12}px`);
      stage.style.setProperty("--tilt-x", `${y * -2.2}deg`);
      stage.style.setProperty("--tilt-y", `${x * 2.8}deg`);
    }

    function onLeave() {
      stage?.style.setProperty("--parallax-x", "0px");
      stage?.style.setProperty("--parallax-y", "0px");
      stage?.style.setProperty("--tilt-x", "0deg");
      stage?.style.setProperty("--tilt-y", "0deg");
    }

    stage.addEventListener("mousemove", onMove);
    stage.addEventListener("mouseleave", onLeave);
    return () => {
      stage.removeEventListener("mousemove", onMove);
      stage.removeEventListener("mouseleave", onLeave);
    };
  }, []);

  const active = scenes[index];

  return (
    <div
      className={`hero-stage tone-${active.tone}`}
      ref={stageRef}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
    >
      <div className="hero-stage-glow" />
      <div className="hero-photo-stack">
        {scenes.map((scene, i) => (
          <div
            className={`hero-photo${i === index ? " is-active" : ""}`}
            key={scene.src}
            aria-hidden={i !== index}
          >
            <Image
              src={scene.src}
              alt=""
              fill
              className="hero-photo-image"
              priority={i === 0}
              sizes="(max-width: 900px) 100vw, 1180px"
            />
          </div>
        ))}
        <div className="hero-photo-grade" />
        <div className="hero-photo-shade" />
        <div className="hero-photo-vignette" />
      </div>

      <div className="hero-float-layer hero-float-layer-desktop" aria-hidden="true">
        {active.cards.map((card, cardIndex) => (
          <article
            className={`hero-float-card float-${card.spot}`}
            key={`${index}-${card.id}`}
            style={{ animationDelay: `${cardIndex * 0.08}s` }}
          >
            <span>{card.label}</span>
            <strong>{card.value}</strong>
            <small>{card.meta}</small>
          </article>
        ))}
      </div>

      <div className="hero-card-stack" aria-label="Live-shaped API previews">
        <p className="hero-card-stack-label">Live-shaped preview</p>
        <ol className="hero-card-stack-list">
          {active.cards.map((card, cardIndex) => (
            <li key={`${index}-${card.id}-stack`}>
              {cardIndex > 0 ? <span className="hero-card-connector" aria-hidden="true" /> : null}
              <article className="hero-float-card hero-stack-card">
                <span>{card.label}</span>
                <strong>{card.value}</strong>
                <small>{card.meta}</small>
              </article>
            </li>
          ))}
        </ol>
      </div>

      <div className="hero-scene-dots" role="tablist" aria-label="Hero scenes" suppressHydrationWarning>
        {scenes.map((scene, i) => (
          <button
            key={scene.src}
            type="button"
            role="tab"
            aria-selected={ready ? i === index : i === 0}
            aria-label={scene.alt}
            className={(ready ? i === index : i === 0) ? "hero-scene-dot is-active" : "hero-scene-dot"}
            // Browser tooling/extensions may inject attributes (e.g. data-cursor-ref) before hydrate.
            suppressHydrationWarning
            onClick={() => {
              setPaused(true);
              setIndex(i);
            }}
          />
        ))}
      </div>
      <div className={`hero-progress${paused ? " is-paused" : ""}`} aria-hidden="true">
        <span key={index} />
      </div>
    </div>
  );
}
