"use client";

import { useId } from "react";

export function BrandMark() {
  const uid = useId().replace(/:/g, "");
  const heartId = `brandHeart-${uid}`;
  const pulseId = `brandPulse-${uid}`;

  return (
    <span className="brand-mark" aria-hidden="true">
      <svg className="brand-mark-icon" viewBox="0 0 40 40" fill="none">
        <defs>
          <linearGradient id={heartId} x1="8" y1="4" x2="34" y2="36" gradientUnits="userSpaceOnUse">
            <stop stopColor="#089f7f" />
            <stop offset="0.55" stopColor="#047adb" />
            <stop offset="1" stopColor="#06b6d4" />
          </linearGradient>
          <linearGradient id={pulseId} x1="9" y1="18" x2="31" y2="24" gradientUnits="userSpaceOnUse">
            <stop stopColor="#ffffff" />
            <stop offset="1" stopColor="#dff0ff" />
          </linearGradient>
        </defs>
        <path
          d="M20 3.5c-8.2 0-14.5 6.5-14.5 14.8C5.5 29 20 37 20 37s14.5-8 14.5-18.7C34.5 10 28.2 3.5 20 3.5Z"
          fill={`url(#${heartId})`}
        />
        <path
          d="M9.5 21h6l2.7-6.5 4.1 12 2.6-7h5.6"
          stroke={`url(#${pulseId})`}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2.3"
        />
        <circle cx="34" cy="5.5" r="3.5" fill="#047adb" stroke="#fff" strokeWidth="1.2" />
      </svg>
      <span className="brand-mark-copy">
        <span className="brand-mark-name">Healthomatix</span>
        <span className="brand-mark-tagline">HEALTHY LIFE, AUTOMATED</span>
      </span>
    </span>
  );
}
