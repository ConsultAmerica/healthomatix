"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";

const scenes = [
  {
    src: "/photos/hero-1.jpg",
    alt: "Clinician reviewing care details with a patient",
    tone: "teal",
    cards: [
      { id: "clinic", label: "ClinicRead", value: "Northside Family Care", meta: "tenant · location · timezone", spot: "clinic" },
      { id: "appt", label: "AppointmentRead", value: "Thu 10:30 · Dr. Patel", meta: "status: scheduled", spot: "appt" },
      { id: "consent", label: "ConsentRead", value: "scope: visit_summary", meta: "policy v2.1 · granted", spot: "consent" },
    ],
  },
  {
    src: "/photos/hero-2.jpg",
    alt: "Care professional in a bright modern clinic",
    tone: "blue",
    cards: [
      { id: "ready", label: "Readiness", value: "3 gates open", meta: "onboarding · team · schedule", spot: "clinic" },
      { id: "cred", label: "CredentialRead", value: "2 pending review", meta: "clinic reviewer only", spot: "appt" },
      { id: "member", label: "MemberRead", value: "12 care team seats", meta: "InvitationRead codes ready", spot: "consent" },
    ],
  },
  {
    src: "/photos/hero-3.jpg",
    alt: "Modern hospital corridor with natural light",
    tone: "cyan",
    cards: [
      { id: "space", label: "LocationRead", value: "Main Street Clinic", meta: "timezone-aware rooms", spot: "clinic" },
      { id: "avail", label: "AvailabilityRead", value: "8 open slots today", meta: "provider-bound", spot: "appt" },
      { id: "invite", label: "InvitationRead", value: "single-use join codes", meta: "secure outside channel", spot: "consent" },
    ],
  },
  {
    src: "/photos/hero-4.jpg",
    alt: "Hands-on clinical care in a calm setting",
    tone: "mint",
    cards: [
      { id: "patient", label: "PatientProfileRead", value: "•••••• · masked", meta: "sign-in required", spot: "clinic" },
      { id: "visit", label: "AppointmentRead", value: "Next visit · Mon 14:00", meta: "timezone-aware", spot: "appt" },
      { id: "scope", label: "ConsentRead", value: "care_coordination", meta: "scope trimmed at query time", spot: "consent" },
    ],
  },
];

export function HeroStage() {
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);
  const stageRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (paused) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const id = window.setInterval(() => {
      setIndex((current) => (current + 1) % scenes.length);
    }, 5800);
    return () => window.clearInterval(id);
  }, [paused]);

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

      <div className="hero-float-layer">
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

      <div className="hero-scene-dots" role="tablist" aria-label="Hero scenes">
        {scenes.map((scene, i) => (
          <button
            key={scene.src}
            type="button"
            role="tab"
            aria-selected={i === index}
            aria-label={scene.alt}
            className={i === index ? "hero-scene-dot is-active" : "hero-scene-dot"}
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
