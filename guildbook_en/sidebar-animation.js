(function() {
  var nav = document.getElementById('sidebar-nav');
  if (!nav) return;
  var parts = location.pathname.split('/');
  var inPages = parts[parts.length - 2] === 'pages';
  var pp = inPages ? '' : 'pages/';       /* prefix for sibling page links */
  var home = inPages ? '../animation.html' : 'animation.html';
  var rootRef = inPages ? '../' : '';     /* prefix for root-level assets */
  if (inPages) { document.write('<script src="' + rootRef + 'topnav.js"><\/script>'); }
  nav.innerHTML = [
    '<a class="nav-item nav-home" href="' + rootRef + 'index.html">← Home</a>',
    '<div class="sidebar-section">Animation Design</div>',
    '<a class="nav-item" href="' + home + '">Animation Production &amp; Syntax</a>',
    '<div class="sidebar-section">Production</div>',
    '<a class="nav-item" href="' + pp + 'anim-制作.html">Animation Production Workflow</a>',
    '<div class="sidebar-section">Syntax</div>',
    '<a class="nav-item" href="' + pp + 'anim-语法.html">Syntax Overview</a>',
    '<a class="nav-item" href="' + pp + 'anim-animaconf.html">animaconf</a>',
    '<a class="nav-item" href="' + pp + 'anim-frame.html">frame</a>',
    '<a class="nav-item" href="' + pp + 'anim-base.html">base</a>',
    '<a class="nav-item" href="' + pp + 'anim-pal.html">pal</a>',
    '<div class="sidebar-section">Related Mechanics</div>',
    '<a class="nav-item" href="' + pp + 'mc05-动画机制.html">Animation Mechanics</a>',
    '<a class="nav-item nav-other" href="' + rootRef + 'scripts.html">Game Scenario →</a>',
    '<a class="nav-item nav-other" href="' + rootRef + 'manual.html">Basic Concepts →</a>',
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
