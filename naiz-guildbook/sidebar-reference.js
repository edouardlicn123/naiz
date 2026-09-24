(function() {
  var nav = document.getElementById('sidebar-nav');
  if (!nav) return;
  var parts = location.pathname.split('/');
  var inPages = parts[parts.length - 2] === 'pages';
  var pp = inPages ? '' : 'pages/';       /* prefix for sibling page links */
  var home = inPages ? '../manual.html' : 'manual.html';
  var rootRef = inPages ? '../' : '';     /* prefix for root-level assets */
  if (inPages) { document.write('<script src="' + rootRef + 'topnav.js"><\/script>'); }
  var other = inPages ? '../scripts.html' : 'scripts.html';
  nav.innerHTML = [
    '<a class="nav-item nav-home" href="' + rootRef + 'index.html">← 总目录</a>',
    '<div class="sidebar-section">基础</div>',
    '<a class="nav-item" href="' + pp + 'fd01-引擎基本概念.html">引擎基本概念</a>',
    '<div class="sidebar-section">UI</div>',
    '<a class="nav-item" href="' + pp + 'ui01-主菜单设计.html">主菜单设计</a>',
    '<a class="nav-item" href="' + pp + 'ui02-设置系统设计.html">设置系统设计</a>',
    '<div class="sidebar-section">机制</div>',
    '<a class="nav-item" href="' + pp + 'mc02-立绘与角色.html">立绘与角色</a>',
    '<a class="nav-item" href="' + pp + 'mc03-图层渲染与换装机制.html">图层渲染与换装</a>',
    '<a class="nav-item" href="' + pp + 'mc04-MAG图片机制.html">MAG 图片机制</a>',
    '<a class="nav-item" href="' + pp + 'mc05-动画机制.html">动画机制</a>',
    '<div class="sidebar-section">配置</div>',
    '<a class="nav-item" href="' + pp + 'cf01-变量系统.html">变量系统</a>',
    '<a class="nav-item" href="' + pp + 'cf02-项目配置文件.html">项目配置文件</a>',
    '<a class="nav-item" href="' + pp + 'cf03-对话框样式方案.html">对话框样式方案</a>',
    '<a class="nav-item" href="' + pp + 'cf04-按钮样式方案.html">按钮样式方案</a>',
    '<a class="nav-item" href="' + pp + 'cf05-过渡效果.html">过渡效果</a>',
    '<a class="nav-item" href="' + pp + 'cf06-黑花字.html">黑花字</a>',
    '<a class="nav-item nav-other" href="' + other + '">游戏剧本 →</a>',
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
