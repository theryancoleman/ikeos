(function () {
  'use strict';

  var TYPE_COLOR = { bug: '#ef4444', idea: '#a855f7', note: '#3b82f6', hub: '#e2c97e', component: '#6b7280' };
  var STATUS_OPACITY = { done: 0.25, deferred: 0.2 };
  var URGENCY_RADIUS = { critical: 12, high: 10, medium: 8, low: 6 };

  var PROJECT_PALETTE = [
    '#6366f1', '#a855f7', '#ec4899', '#3b82f6',
    '#10b981', '#f59e0b', '#ef4444', '#14b8a6',
  ];

  function padHull(pts, pad) {
    var cx = 0, cy = 0;
    pts.forEach(function (p) { cx += p[0]; cy += p[1]; });
    cx /= pts.length; cy /= pts.length;
    return pts.map(function (p) {
      var dx = p[0] - cx, dy = p[1] - cy;
      var len = Math.sqrt(dx * dx + dy * dy) || 1;
      return [p[0] + dx / len * pad, p[1] + dy / len * pad];
    });
  }

  function circlePath(cx, cy, r) {
    return 'M' + (cx - r) + ',' + cy +
      'a' + r + ',' + r + ' 0 1,0 ' + (r * 2) + ',0' +
      'a' + r + ',' + r + ' 0 1,0 -' + (r * 2) + ',0';
  }

  function projectLabel(slug) {
    return slug.replace(/-/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  var allNodes = [];
  var allLinks = [];
  var simulation = null;

  function nodeRadius(d) { return URGENCY_RADIUS[d.urgency] || 7; }
  function nodeOpacity(d) { return STATUS_OPACITY[d.status] || 1; }
  function entryUrl(d) {
    if (!d.project) return null;
    if (d.type === 'hub') return '/projects/' + d.project;
    if (d.type === 'component') return null;
    return '/projects/' + d.project + '/' + d.id;
  }

  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Health sidebar ──────────────────────────────────────────────────────────

  function renderHealth(health) {
    var untriaged = health.untriaged;
    var stale = health.stale;
    var broken = health.broken_links;

    document.getElementById('badge-untriaged').textContent = untriaged.length;
    document.getElementById('badge-stale').textContent = stale.length;
    document.getElementById('badge-broken').textContent = broken.length;

    function entryItem(e, sub) {
      return '<li class="health-item"><a href="/projects/' + e.project + '/' + e.slug + '">' +
        escHtml(e.title) + '</a>' +
        (sub ? '<span class="health-sub">' + escHtml(sub) + '</span>' : '') +
        '</li>';
    }

    document.getElementById('list-untriaged').innerHTML =
      untriaged.length
        ? untriaged.slice(0, 25).map(function (e) { return entryItem(e, e.project); }).join('')
        : '<li class="health-empty">All clear</li>';

    document.getElementById('list-stale').innerHTML =
      stale.length
        ? stale.slice(0, 25).map(function (e) {
            return entryItem(e, e.days_stale + 'd stale · ' + e.project);
          }).join('')
        : '<li class="health-empty">All clear</li>';

    document.getElementById('list-broken').innerHTML =
      broken.length
        ? broken.slice(0, 25).map(function (b) {
            return '<li class="health-item health-item-broken">[[' + escHtml(b.broken_ref) + ']]' +
              '<span class="health-sub">in ' + escHtml(b.source_project) + '</span></li>';
          }).join('')
        : '<li class="health-empty">All clear</li>';
  }

  // ── Force graph ─────────────────────────────────────────────────────────────

  function filteredData() {
    var showBugs  = document.getElementById('filter-bugs').checked;
    var showIdeas = document.getElementById('filter-ideas').checked;
    var showNotes = document.getElementById('filter-notes').checked;

    var visibleIds = new Set(
      allNodes
        .filter(function (n) {
          return (n.type === 'bug'  && showBugs)  ||
                 (n.type === 'idea' && showIdeas) ||
                 (n.type === 'note' && showNotes) ||
                 n.type === 'hub';
        })
        .map(function (n) { return n.id; })
    );

    return {
      nodes: allNodes.filter(function (n) { return visibleIds.has(n.id); }),
      links: allLinks.filter(function (l) {
        var src = (l.source && l.source.id !== undefined) ? l.source.id : l.source;
        var tgt = (l.target && l.target.id !== undefined) ? l.target.id : l.target;
        return visibleIds.has(src) && visibleIds.has(tgt);
      }),
    };
  }

  function renderGraph() {
    var wrap = document.querySelector('.graph-canvas-wrap');
    var W = wrap.clientWidth;
    var H = Math.max(520, window.innerHeight - 220);

    var svg = d3.select('#graph-svg').attr('width', W).attr('height', H);
    svg.selectAll('*').remove();

    if (simulation) { simulation.stop(); simulation = null; }

    var fd = filteredData();
    if (fd.nodes.length === 0) return;

    // Clone nodes so D3 can mutate x/y without affecting allNodes
    var nodeData = fd.nodes.map(function (n) { return Object.assign({}, n); });
    var byId = new Map(nodeData.map(function (n) { return [n.id, n]; }));
    var linkData = fd.links
      .map(function (l) {
        var src = (l.source && l.source.id !== undefined) ? l.source.id : l.source;
        var tgt = (l.target && l.target.id !== undefined) ? l.target.id : l.target;
        return { source: byId.get(src), target: byId.get(tgt) };
      })
      .filter(function (l) { return l.source && l.target; });

    // Cluster centres: spread projects across the canvas in a grid
    var projects = Array.from(new Set(nodeData.map(function (n) { return n.project; })));
    var cols = Math.ceil(Math.sqrt(projects.length));
    var rows = Math.ceil(projects.length / cols);
    var clusterX = {}, clusterY = {};
    projects.forEach(function (p, i) {
      clusterX[p] = W * (0.1 + 0.8 * ((i % cols + 0.5) / cols));
      clusterY[p] = H * (0.1 + 0.8 * ((Math.floor(i / cols) + 0.5) / rows));
    });

    simulation = d3.forceSimulation(nodeData)
      .force('link', d3.forceLink(linkData).id(function (d) { return d.id; }).distance(70))
      .force('charge', d3.forceManyBody().strength(-90))
      .force('collide', d3.forceCollide().radius(function (d) { return nodeRadius(d) + 4; }))
      .force('x', d3.forceX(function (d) { return clusterX[d.project] || W / 2; }).strength(0.07))
      .force('y', d3.forceY(function (d) { return clusterY[d.project] || H / 2; }).strength(0.07));

    var g = svg.append('g');

    // Pan + zoom
    svg.call(
      d3.zoom()
        .scaleExtent([0.15, 5])
        .on('zoom', function (event) { g.attr('transform', event.transform); })
    );

    // ── Project hull overlays ────────────────────────────────────────────────
    var projectColors = {};
    projects.forEach(function (p, i) { projectColors[p] = PROJECT_PALETTE[i % PROJECT_PALETTE.length]; });

    var hullG = g.append('g');
    var hullPaths = [], hullLabels = [];
    var labelG = g.append('g');

    projects.forEach(function (proj) {
      var col = projectColors[proj];
      hullPaths.push(
        hullG.append('path')
          .attr('fill', col).attr('fill-opacity', 0.07)
          .attr('stroke', col).attr('stroke-opacity', 0.22)
          .attr('stroke-width', 1.5).attr('stroke-linejoin', 'round')
      );
      hullLabels.push(
        labelG.append('text')
          .text(projectLabel(proj))
          .attr('fill', col).attr('fill-opacity', 0.5)
          .attr('font-size', '10px').attr('text-anchor', 'middle')
          .attr('letter-spacing', '0.06em').attr('pointer-events', 'none')
      );
    });

    function updateHulls() {
      var PAD = 22;
      projects.forEach(function (proj, i) {
        var pts = nodeData
          .filter(function (n) { return n.project === proj && n.x != null; })
          .map(function (n) { return [n.x, n.y]; });

        if (pts.length === 0) { hullPaths[i].attr('d', null); hullLabels[i].attr('display', 'none'); return; }

        var cx = pts.reduce(function (s, p) { return s + p[0]; }, 0) / pts.length;
        var cy = pts.reduce(function (s, p) { return s + p[1]; }, 0) / pts.length;
        hullLabels[i].attr('x', cx).attr('y', cy).attr('display', null);

        var d;
        if (pts.length < 3) {
          var r = pts.length === 1 ? PAD + 8 :
            Math.sqrt(Math.pow(pts[0][0] - pts[1][0], 2) + Math.pow(pts[0][1] - pts[1][1], 2)) / 2 + PAD;
          d = circlePath(cx, cy, r);
        } else {
          var hull = d3.polygonHull(pts);
          if (!hull) { hullPaths[i].attr('d', null); return; }
          var padded = padHull(hull, PAD);
          d = 'M' + padded.map(function (p) { return p[0].toFixed(1) + ',' + p[1].toFixed(1); }).join('L') + 'Z';
        }
        hullPaths[i].attr('d', d);
      });
    }

    // Edges
    var link = g.append('g')
      .selectAll('line')
      .data(linkData)
      .join('line')
      .attr('stroke', '#3d3d3d')
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.7);

    var tooltip = document.getElementById('graph-tooltip');

    // Nodes
    var node = g.append('g')
      .selectAll('circle')
      .data(nodeData)
      .join('circle')
      .attr('r', nodeRadius)
      .attr('fill', function (d) { return TYPE_COLOR[d.type] || '#888'; })
      .attr('fill-opacity', nodeOpacity)
      .attr('stroke', '#111')
      .attr('stroke-width', 1)
      .style('cursor', function (d) { return d.type === 'component' ? 'not-allowed' : 'pointer'; })
      .on('mouseover', function (event, d) {
        tooltip.style.display = 'block';
        tooltip.innerHTML =
          '<strong>' + escHtml(d.title) + '</strong><br>' +
          escHtml(d.project) + ' · ' + escHtml(d.type) + ' · ' + escHtml(d.status);
      })
      .on('mousemove', function (event) {
        var rect = wrap.getBoundingClientRect();
        tooltip.style.left = (event.clientX - rect.left + 14) + 'px';
        tooltip.style.top  = (event.clientY - rect.top  + 14) + 'px';
      })
      .on('mouseout', function () { tooltip.style.display = 'none'; })
      .on('click', function (event, d) {
        if (d._dragged) { d._dragged = false; return; }
        var url = entryUrl(d); if (url) window.location.href = url;
      })
      .call(
        d3.drag()
          .on('start', function (event, d) {
            d._dragged = false;
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
          })
          .on('drag', function (event, d) { d._dragged = true; d.fx = event.x; d.fy = event.y; })
          .on('end', function (event, d) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null; d.fy = null;
          })
      );

    simulation.on('tick', function () {
      updateHulls();
      link
        .attr('x1', function (d) { return d.source.x; })
        .attr('y1', function (d) { return d.source.y; })
        .attr('x2', function (d) { return d.target.x; })
        .attr('y2', function (d) { return d.target.y; });
      node
        .attr('cx', function (d) { return d.x; })
        .attr('cy', function (d) { return d.y; });
    });
  }

  // ── Init ────────────────────────────────────────────────────────────────────

  async function init() {
    var loadingEl = document.getElementById('graph-loading');
    try {
      var res = await fetch('/api/graph');
      if (!res.ok) throw new Error('API error: ' + res.status);
      var data = await res.json();
      allNodes = data.nodes;
      allLinks = data.links;

      if (loadingEl) loadingEl.style.display = 'none';

      var projectCount = new Set(allNodes.map(function (n) { return n.project; })).size;
      var subtitle = document.getElementById('graph-subtitle');
      if (subtitle) {
        subtitle.textContent = allNodes.length + ' entries across ' + projectCount + ' projects — connections show wikilinks.';
      }

      renderHealth(data.health);
      renderGraph();

      ['filter-bugs', 'filter-ideas', 'filter-notes'].forEach(function (id) {
        document.getElementById(id).addEventListener('change', renderGraph);
      });

      window.addEventListener('resize', renderGraph);
    } catch (err) {
      if (loadingEl) loadingEl.textContent = 'Failed to load graph data.';
      console.error(err);
    }
  }

  init();
})();
