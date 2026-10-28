export function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg
        className="brand-mark-icon"
        viewBox="0 0 64 64"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        aria-hidden="true"
      >
        {/* Brand-sheet leaf: upright droplet with soft left inset */}
        <path
          className="brand-mark-leaf"
          d="M33.2 4.8c11.2 3.6 19.6 15.2 18.8 28.4C51.2 48.4 40.4 58.4 27.6 59c-2.6.1-4.4-2.1-3.9-4.5C26.2 39.6 21.6 26.4 11.2 18.2 16.4 10.4 24.4 6 33.2 4.8Z"
        />
        {/* ECG pulse — white cut through the leaf */}
        <path
          className="brand-mark-pulse"
          d="M14 33.2h9.6l3.6-8.8 5.4 17.6 3.8-9.6H50"
          strokeWidth="3.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Coral vitality accent */}
        <circle className="brand-mark-accent" cx="50.4" cy="11.2" r="4.4" />
      </svg>
      <span className="brand-mark-copy">
        <span className="brand-mark-wordmark">
          <span className="brand-mark-health">Health</span>
          <span className="brand-mark-omatix">omatix</span>
        </span>
      </span>
    </span>
  );
}
