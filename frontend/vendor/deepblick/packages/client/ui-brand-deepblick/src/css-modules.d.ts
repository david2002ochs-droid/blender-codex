/** CSS module class names emitted by the browser bundler. */
declare module '*.module.css' {
  const classes: Record<string, string>
  export default classes
}

/** Local application logos bundled as data URLs. */
declare module '*.svg' {
  const url: string
  export default url
}

/** Self-hosted variable-font bytes bundled as data URLs. */
declare module '*.woff2' {
  const url: string
  export default url
}
