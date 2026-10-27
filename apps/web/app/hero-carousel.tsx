"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

const slides = [
  {
    image: "/care-connections.svg",
    alt: "Illustration of a patient and care professional",
    title: "Patient and clinic",
    detail: "A more connected experience",
  },
  {
    image: "/care-appointments.svg",
    alt: "Illustration of a patient reviewing a calendar",
    title: "A clearer path",
    detail: "Scheduling is not available in this preview",
  },
  {
    image: "/care-team.svg",
    alt: "Illustration of a care team reviewing a patient visit",
    title: "Care team tools",
    detail: "Designed for clinic workflows",
  },
  {
    image: "/care-dashboard.svg",
    alt: "Illustration of a care dashboard with abstract charts and status cards",
    title: "A clearer overview",
    detail: "Thoughtful views for everyday care",
  },
  {
    image: "/care-imaging.svg",
    alt: "Illustration of a care professional reviewing an abstract medical scan",
    title: "Imaging, made clearer",
    detail: "Designed to keep important details in view",
  },
];

export function HeroCarousel() {
  const [activeSlide, setActiveSlide] = useState(0);
  const [paused, setPaused] = useState(false);
  const [pointerPaused, setPointerPaused] = useState(false);
  const [focusPaused, setFocusPaused] = useState(false);

  useEffect(() => {
    if (
      paused ||
      pointerPaused ||
      focusPaused ||
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    ) {
      return;
    }

    const timer = window.setInterval(() => {
      setActiveSlide((current) => (current + 1) % slides.length);
    }, 6000);

    return () => window.clearInterval(timer);
  }, [focusPaused, paused, pointerPaused]);

  const slide = slides[activeSlide];

  return (
    <div
      aria-label="Healthomatix care highlights"
      aria-roledescription="carousel"
      className="hero-art"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setFocusPaused(false);
        }
      }}
      role="region"
      onFocus={() => setFocusPaused(true)}
      onPointerEnter={() => setPointerPaused(true)}
      onPointerMove={(event) => {
        if (
          event.pointerType !== "mouse" ||
          window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ) {
          return;
        }

        const bounds = event.currentTarget.getBoundingClientRect();
        const x = (event.clientX - bounds.left) / bounds.width - 0.5;
        const y = (event.clientY - bounds.top) / bounds.height - 0.5;

        event.currentTarget.style.setProperty("--image-x", `${x * 12}px`);
        event.currentTarget.style.setProperty("--image-y", `${y * 12}px`);
        event.currentTarget.style.setProperty("--backdrop-x", `${x * -18}px`);
        event.currentTarget.style.setProperty("--backdrop-y", `${y * -18}px`);
      }}
      onPointerLeave={(event) => {
        event.currentTarget.style.setProperty("--image-x", "0px");
        event.currentTarget.style.setProperty("--image-y", "0px");
        event.currentTarget.style.setProperty("--backdrop-x", "0px");
        event.currentTarget.style.setProperty("--backdrop-y", "0px");
        setPointerPaused(false);
      }}
    >
      <div className="hero-art-backdrop" aria-hidden="true" />
      <span className="hero-orbit hero-orbit-one" aria-hidden="true" />
      <span className="hero-orbit hero-orbit-two" aria-hidden="true" />
      <div
        aria-label={`Slide ${activeSlide + 1} of ${slides.length}: ${slide.title}`}
        aria-roledescription="slide"
        className="hero-image-frame"
        role="group"
      >
        <div className="hero-image-motion" key={slide.image}>
          <Image
            src={slide.image}
            alt={slide.alt}
            width={680}
            height={570}
            loading="eager"
            sizes="(max-width: 640px) 100vw, (max-width: 900px) 80vw, 48vw"
            className="hero-illustration"
          />
        </div>
        <div className="floating-note">
          <span className="floating-note-icon" aria-hidden="true">+</span>
          <span>
            <strong>{slide.title}</strong>
            <small>{slide.detail}</small>
          </span>
        </div>
      </div>
      <div className="carousel-controls" aria-label="Care highlight controls" role="group">
        <button
          aria-label={paused ? "Resume automatic highlights" : "Pause automatic highlights"}
          aria-pressed={paused}
          className="carousel-arrow carousel-play-toggle"
          onClick={() => {
            if (paused) {
              setFocusPaused(false);
            }
            setPaused(!paused);
          }}
          type="button"
        >
          <span aria-hidden="true">{paused ? "▶" : "Ⅱ"}</span>
        </button>
        <button
          aria-label="Previous care highlight"
          className="carousel-arrow"
          onClick={() => setActiveSlide((current) => (current + slides.length - 1) % slides.length)}
          type="button"
        >
          <span aria-hidden="true">←</span>
        </button>
        <div className="carousel-dots">
          {slides.map((item, index) => (
            <button
              aria-current={activeSlide === index ? "true" : undefined}
              aria-label={`Show highlight ${index + 1}: ${item.title}`}
              className={activeSlide === index ? "carousel-dot active" : "carousel-dot"}
              key={item.image}
              onClick={() => setActiveSlide(index)}
              type="button"
            />
          ))}
        </div>
        <button
          aria-label="Next care highlight"
          className="carousel-arrow"
          onClick={() => setActiveSlide((current) => (current + 1) % slides.length)}
          type="button"
        >
          <span aria-hidden="true">→</span>
        </button>
      </div>
    </div>
  );
}
