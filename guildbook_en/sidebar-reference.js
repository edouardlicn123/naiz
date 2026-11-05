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
    '<a class="nav-item nav-home" href="' + rootRef + 'index.html">← Home</a>',
    '<div class="sidebar-section">Basics</div>',
    '<a class="nav-item" href="' + pp + 'fd01-引擎基本概念.html">Engine Basic Concepts</a>',
    '<div class="sidebar-section">UI</div>',
    '<a class="nav-item" href="' + pp + 'ui01-主菜单设计.html">Main Menu Design</a>',
    '<a class="nav-item" href="' + pp + 'ui02-设置系统设计.html">Settings System Design</a>',
    '<div class="sidebar-section">Mechanics</div>',
    '<a class="nav-item" href="' + pp + 'mc02-立绘与角色.html">Character Sprites &amp; Roles</a>',
    '<a class="nav-item" href="' + pp + 'mc03-图层渲染与换装机制.html">Layer Rendering &amp; Costume Change</a>',
    '<a class="nav-item" href="' + pp + 'mc04-MAG图片机制.html">MAG Image Mechanics</a>',
    '<a class="nav-item" href="' + pp + 'mc05-动画机制.html">Animation Mechanics</a>',
    '<a class="nav-item" href="' + pp + 'mc06-音频通路机制.html">Audio Path Mechanics</a>',
    '<a class="nav-item" href="' + pp + 'mc07-音频平台与工具.html">Audio Platforms &amp; Tools</a>',
    '<div class="sidebar-section">Configuration</div>',
    '<a class="nav-item" href="' + pp + 'cf01-变量系统.html">Variable System</a>',
    '<a class="nav-item" href="' + pp + 'cf02-项目配置文件.html">Project Configuration File</a>',
    '<a class="nav-item" href="' + pp + 'cf03-对话框样式方案.html">Dialogue Box Style Scheme</a>',
    '<a class="nav-item" href="' + pp + 'cf04-按钮样式方案.html">Button Style Scheme</a>',
    '<a class="nav-item" href="' + pp + 'cf05-过渡效果.html">Transition Settings</a>',
    '<a class="nav-item" href="' + pp + 'cf06-黑花字.html">Blackletter</a>',
    '<a class="nav-item" href="' + pp + 'cf07-图片登记.html">Image Registration</a>',
    '<a class="nav-item nav-other" href="' + other + '">Game Scenario →</a>',
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
