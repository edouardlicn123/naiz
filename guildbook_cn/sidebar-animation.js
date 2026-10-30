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
    '<a class="nav-item nav-home" href="' + rootRef + 'index.html">← 总目录</a>',
    '<div class="sidebar-section">动画设计</div>',
    '<a class="nav-item" href="' + home + '">动画制作与语法</a>',
    '<div class="sidebar-section">制作</div>',
    '<a class="nav-item" href="' + pp + 'anim-制作.html">动画制作工作流</a>',
    '<div class="sidebar-section">语法</div>',
    '<a class="nav-item" href="' + pp + 'anim-语法.html">语法总览</a>',
    '<a class="nav-item" href="' + pp + 'anim-animaconf.html">animaconf</a>',
    '<a class="nav-item" href="' + pp + 'anim-frame.html">frame</a>',
    '<a class="nav-item" href="' + pp + 'anim-base.html">base</a>',
    '<a class="nav-item" href="' + pp + 'anim-pal.html">pal</a>',
    '<div class="sidebar-section">相关机制</div>',
    '<a class="nav-item" href="' + pp + 'mc05-动画机制.html">动画机制</a>',
    '<a class="nav-item nav-other" href="' + rootRef + 'scripts.html">游戏剧本 →</a>',
    '<a class="nav-item nav-other" href="' + rootRef + 'manual.html">基本概念 →</a>',
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
