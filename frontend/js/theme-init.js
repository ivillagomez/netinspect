/**
 * Theme initialisation — must run synchronously before first paint to prevent
 * a flash of the wrong theme.  Loaded as a plain <script> (no defer/async) so
 * the browser blocks rendering until this executes.
 *
 * Extracted from index.html so the Content-Security-Policy can use
 * script-src 'self' instead of 'unsafe-inline'.
 */
(function () {
  var t = localStorage.getItem('netinspect_theme');
  if (t === 'light') document.documentElement.setAttribute('data-theme', 'light');
})();
