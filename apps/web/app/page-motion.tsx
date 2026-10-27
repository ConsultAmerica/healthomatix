"use client";

import { useEffect } from "react";

const SECTION_IDS = [
  "overview",
  "features",
  "applications",
  "objects",
  "connections",
  "approach",
  "faq",
];

export function PageMotion() {
  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const reveals = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));

    if (!reduce && "IntersectionObserver" in window) {
      const revealObserver = new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-revealed");
              revealObserver.unobserve(entry.target);
            }
          }
        },
        { threshold: 0.14, rootMargin: "0px 0px -8% 0px" },
      );
      for (const node of reveals) revealObserver.observe(node);

      return () => revealObserver.disconnect();
    }

    for (const node of reveals) node.classList.add("is-revealed");
  }, []);

  useEffect(() => {
    const links = Array.from(
      document.querySelectorAll<HTMLAnchorElement>(".page-rail a[href^='#']"),
    );
    if (!links.length) return;

    const sections = SECTION_IDS
      .map((id) => document.getElementById(id))
      .filter((node): node is HTMLElement => Boolean(node));

    function setActive(id: string) {
      for (const link of links) {
        const match = link.getAttribute("href") === `#${id}`;
        link.classList.toggle("is-active", match);
      }
    }

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
        if (visible[0]?.target.id) setActive(visible[0].target.id);
      },
      { threshold: [0.2, 0.45, 0.7], rootMargin: "-20% 0px -45% 0px" },
    );

    for (const section of sections) observer.observe(section);
    setActive("overview");

    return () => observer.disconnect();
  }, []);

  return null;
}
