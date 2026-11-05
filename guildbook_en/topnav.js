(function() {
  if (document.getElementById('topnav')) return;
  var path = location.pathname;
  var file = path.split('/').pop();
  var inPages = path.indexOf('/pages/') !== -1;
  var cat = '';
  if (inPages) {
    if (/^(fd|ui|mc|cf)/.test(file)) cat = 'basic';
    else if (/^sc/.test(file)) cat = 'script';
    else if (/^anim/.test(file)) cat = 'anim';
    else if (/^tool/.test(file)) cat = 'tool';
  } else {
    if (file === 'manual.html') cat = 'basic';
    else if (file === 'scripts.html') cat = 'script';
    else if (file === 'animation.html') cat = 'anim';
    else if (file === 'tools.html') cat = 'tool';
  }
  var items = [
    { key: 'basic',  label: 'Basic Concepts', href: 'manual.html' },
    { key: 'tool',  label: 'Production Tools', href: 'tools.html' },
    { key: 'script', label: 'Game Scenario', href: 'scripts.html' },
    { key: 'anim',  label: 'Animation Design', href: 'animation.html' }
  ];
  var base = inPages ? '../' : '';
  var html = '<header class="topnav"><div class="topnav-inner">'
    + '<a class="topnav-brand" href="' + base + 'index.html"><img class="topnav-logo" src="' + base + 'imgs/logo-mini.png" alt="Naiz">Naiz Engine Docs</a>'
    + '<nav class="topnav-links">';
  for (var i = 0; i < items.length; i++) {
    var it = items[i];
    var cls = 'topnav-link' + (it.key === cat ? ' active' : '');
    html += '<a class="' + cls + '" href="' + base + it.href + '">' + it.label + '</a>';
  }
  html += '</nav></div></header>';
  document.body.insertAdjacentHTML('afterbegin', html);
})();
