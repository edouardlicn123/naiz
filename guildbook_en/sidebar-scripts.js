(function() {
  var nav = document.getElementById('sidebar-nav');
  if (!nav) return;
  var parts = location.pathname.split('/');
  var inPages = parts[parts.length - 2] === 'pages';
  var pp = inPages ? '' : 'pages/';       /* prefix for sibling page links */
  var home = inPages ? '../scripts.html' : 'scripts.html';
  var rootRef = inPages ? '../' : '';     /* prefix for root-level assets */
  if (inPages) { document.write('<script src="' + rootRef + 'topnav.js"><\/script>'); }
  var other = inPages ? '../manual.html' : 'manual.html';
  nav.innerHTML = [
    '<a class="nav-item nav-home" href="' + rootRef + 'index.html">← Home</a>',
    '<div class="sidebar-section">Game Scenario</div>',
    '<a class="nav-item" href="' + pp + 'sc01-NB剧本概述.html">NB Scenario Overview</a>',
    '<a class="nav-item" href="' + pp + 'sc02-bg.html">bg Background Switching</a>',
    '<a class="nav-item" href="' + pp + 'sc19-cg.html">cg Full-Screen CG Display</a>',
    '<a class="nav-item" href="' + pp + 'sc03-char.html">char Sprite Operations &amp; Dialogue</a>',
    '<a class="nav-item" href="' + pp + 'sc04-scene.html">scene Scene Jump</a>',
    '<a class="nav-item" href="' + pp + 'sc05-saveload.html">loadscene Loading Saves</a>',
    '<a class="nav-item" href="' + pp + 'sc06-gallery.html">cgvmenu Gallery</a>',
    '<a class="nav-item" href="' + pp + 'sc07-mainmenu.html">mainmenu Main Menu</a>',
    '<a class="nav-item" href="' + pp + 'sc08-question.html">question Choice Branching</a>',
    '<a class="nav-item" href="' + pp + 'sc09-var.html">var Variable Operations</a>',
    '<a class="nav-item" href="' + pp + 'sc10-audio.html">bgm/sound/voice Audio</a>',
    '<a class="nav-item" href="' + pp + 'sc11-sceneconf.html">sceneconf Scene Configuration</a>',
    '<a class="nav-item" href="' + pp + 'sc12-host.html">host System Narration</a>',
    '<a class="nav-item" href="' + pp + 'sc13-startsetting.html">startsetting Startup Settings</a>',
    '<a class="nav-item" href="' + pp + 'sc14-settingmenu.html">settingmenu Settings Menu</a>',
    '<a class="nav-item" href="' + pp + 'sc15-playanima.html">playanima Play Animation</a>',
    '<a class="nav-item" href="' + pp + 'sc16-waitanima.html">waitanima Wait for Animation</a>',
    '<a class="nav-item" href="' + pp + 'sc17-stopanima.html">stopanima Stop Animation</a>',
    '<a class="nav-item" href="' + pp + 'sc18-delay.html">delay Scenario Delay</a>',
    '<a class="nav-item nav-other" href="' + other + '">Basic Concepts →</a>',
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
