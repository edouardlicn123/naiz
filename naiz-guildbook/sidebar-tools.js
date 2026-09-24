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
    '<a class="nav-item nav-home" href="' + rootRef + 'index.html">← 总目录</a>',
    '<div class="sidebar-section">制作工具</div>',
    '<a class="nav-item" href="' + pp + 'tool-start.html">start.sh</a>',
    '<a class="nav-item" href="' + pp + 'tool-makegame.html">makegame.sh</a>',
    '<a class="nav-item" href="' + pp + 'tool-anima.html">anima.sh</a>',
    '<div class="sidebar-section">其他分类</div>',
    '<a class="nav-item nav-other" href="' + rootRef + 'scripts.html">游戏剧本 →</a>',
    '<a class="nav-item nav-other" href="' + rootRef + 'manual.html">基本概念 →</a>',
    '<a class="nav-item nav-other" href="' + rootRef + 'animation.html">动画设计 →</a>',
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
