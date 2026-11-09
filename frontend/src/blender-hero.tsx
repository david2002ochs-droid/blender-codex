import React from 'react';

/** Blender-only artwork adapter; the pinned upstream brand stays untouched. */
export function BlenderHero() {
  return <span className="blender-hero" data-blender-hero>
    <svg className="blender-hero-viewport" viewBox="0 0 600 182" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <g className="blender-hero-grid" fill="none" stroke="currentColor" strokeWidth=".7">
        {[32, 40, 51, 67, 91, 126, 176].map(y => <path key={y} d={`M0 ${y}H600`}/>)}
        {[-900, -500, -220, -60, 60, 160, 240, 300, 360, 440, 540, 660, 820, 1100, 1500].map(x => <path key={x} d={`M300 15L${x} 182`}/>)}
      </g>
      <g className="blender-hero-axes" fill="none" strokeWidth=".85">
        <path d="M0 75L600 146" stroke="#b87368"/>
        <path d="M600 75L0 146" stroke="#7b9d87"/>
      </g>
      <g className="blender-hero-cube" fill="none" stroke="#e88735" strokeWidth="1.4" strokeLinejoin="round">
        <path d="M300 16L322 28L300 41L278 28Z M278 28V53L300 66L322 53V28 M300 41V66"/>
        <path d="M300 16V41 M278 53L300 41L322 53" strokeDasharray="2 3" opacity=".35"/>
        <circle cx="300" cy="41" r="1.8" fill="#e88735" stroke="none"/>
      </g>
    </svg>
    <span className="blender-hero-wordmark">deepblick</span>
    <span className="blender-hero-tagline">Your AI partner for Blender.</span>
  </span>;
}
