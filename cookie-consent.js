(function () {
  var STORAGE_KEY = 'tl_cookie_consent';
  var EXPIRY_DAYS = 365;

  function hasConsented() {
    try {
      var val = localStorage.getItem(STORAGE_KEY);
      if (!val) return false;
      var data = JSON.parse(val);
      return data.accepted && Date.now() < data.expires;
    } catch (e) { return false; }
  }

  function saveConsent() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({
        accepted: true,
        expires: Date.now() + EXPIRY_DAYS * 24 * 60 * 60 * 1000
      }));
    } catch (e) {}
  }

  function dismiss(banner) {
    banner.style.transform = 'translateY(120%)';
    banner.style.opacity = '0';
    setTimeout(function () { banner.remove(); }, 400);
  }

  function init() {
    if (hasConsented()) return;

    var style = document.createElement('style');
    style.textContent = [
      '#tl-cookie{position:fixed;bottom:0;left:0;right:0;z-index:9999;',
      'background:#13203a;border-top:1px solid rgba(255,255,255,0.09);',
      'padding:14px 20px;display:flex;align-items:center;gap:14px;',
      'flex-wrap:wrap;justify-content:space-between;',
      'font-family:"DM Sans",sans-serif;font-size:14px;color:#94A3B8;',
      'transition:transform .35s ease,opacity .35s ease;}',
      '#tl-cookie a{color:#3B82F6;text-decoration:underline;}',
      '#tl-cookie a:hover{color:#60a5fa;}',
      '#tl-cookie-btn{background:#3B82F6;color:#fff;border:none;',
      'border-radius:8px;padding:8px 20px;font-family:"DM Sans",sans-serif;',
      'font-size:14px;font-weight:600;cursor:pointer;white-space:nowrap;',
      'transition:background .2s;}',
      '#tl-cookie-btn:hover{background:#2563eb;}'
    ].join('');
    document.head.appendChild(style);

    var banner = document.createElement('div');
    banner.id = 'tl-cookie';
    banner.innerHTML = [
      '<span>We use essential cookies to keep TechLoop running. No tracking or ads. ',
      '<a href="/privacy.html">Privacy Policy</a></span>',
      '<button id="tl-cookie-btn">Got it</button>'
    ].join('');
    document.body.appendChild(banner);

    document.getElementById('tl-cookie-btn').addEventListener('click', function () {
      saveConsent();
      dismiss(banner);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
