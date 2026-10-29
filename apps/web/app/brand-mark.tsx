/** Brand-sheet mark: leaf + ECG + coral accent, two-tone wordmark, tagline. */
export function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg
        className="brand-mark-icon"
        viewBox="0 0 64 64"
        width={44}
        height={44}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        overflow="visible"
        aria-hidden="true"
      >
        {/*
          Full teardrop leaf (brand sheet), inset in viewBox so the left
          curve never sits on the SVG edge. Stem + ECG + coral accent.
        */}
        <path
          className="brand-mark-leaf"
          d="M32 6
             C41 6.5 49 13 52.5 22
             C56 31 55.5 41 50.5 48.5
             C45.5 56 37.5 59.5 32 59.5
             C26.5 59.5 18.5 56 13.5 48.5
             C8.5 41 8 31 11.5 22
             C15 13 23 6.5 32 6Z"
        />
        <path
          className="brand-mark-pulse"
          d="M12.5 33H22l3.2-7.5 4.8 15.5 3.4-8.5H51"
          strokeWidth="2.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          className="brand-mark-stem"
          d="M32 33.5V52"
          strokeWidth="1.6"
          strokeLinecap="round"
        />
        <circle className="brand-mark-accent" cx="49" cy="12" r="4" />
      </svg>
      <span className="brand-mark-copy">
        <span className="brand-mark-wordmark">
          <span className="brand-mark-health">Health</span>
          <span className="brand-mark-omatix">omatix</span>
        </span>
        <span className="brand-mark-tagline">Healthy life, automated</span>
      </span>
    </span>
  );
}
