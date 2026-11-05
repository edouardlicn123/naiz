(function() {
  var nav = document.getElementById('sidebar-nav');
  if (!nav) return;
  var parts = location.pathname.split('/');
  var inPages = parts[parts.length - 2] === 'pages';
  var pp = inPages ? '' : 'pages/';       /* prefix for sibling page links */
  var home = inPages ? '../tools.html' : 'tools.html';
  var rootRef = inPages ? '../' : '';     /* prefix for root-level assets */
  if (inPages) { document.write('<script src="' + rootRef + 'topnav.js"><\/script>'); }
  nav.innerHTML = [
    '<a class="nav-item nav-home" href="' + rootRef + 'index.html">← Home</a>',
    '<div class="sidebar-section">Production Tools</div>',
    '<a class="nav-item" href="' + pp + 'tool-start.html">start.sh</a>',
    '<a class="nav-item" href="' + pp + 'tool-makegame.html">makegame.sh</a>',
    '<a class="nav-item" href="' + pp + 'tool-anima.html">anima.sh</a>',
    '<a class="nav-item" href="' + pp + 'tool-market.html">market.sh</a>',
    '<div class="sidebar-section">Other Categories</div>',
    '<a class="nav-item nav-other" href="' + rootRef + 'scripts.html">Game Scenario →</a>',
    '<a class="nav-item nav-other" href="' + rootRef + 'manual.html">Basic Concepts →</a>',
    '<a class="nav-item nav-other" href="' + rootRef + 'animation.html">Animation Design →</a>',
  ].join('\n');

  var page = location.pathname.split('/').pop();
  if (!page || page === '') page = 'index.html';
  var links = nav.querySelectorAll('.nav-item');
  for (var i = 0; i < links.length; i++) {
    if (links[i].getAttribute('href').split('/').pop() === page) {
      links[i].classList.add('active');
      break;
    }
  }
})();
