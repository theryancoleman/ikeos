(function () {
  'use strict';

  var TYPE_COLOR = { bug: '#ef4444', idea: '#a855f7', note: '#3b82f6' };
  var STATUS_OPACITY = { done: 0.25, deferred: 0.2 };
  var URGENCY_RADIUS = { critical: 12, high: 10, medium: 8, low: 6 };

  var allNodes = [];
  var allLinks = [];
  var simulation = null;

  function nodeRadius(d) { return URGENCY_RADIUS[d.urgency] || 7; }
  function nodeOpacity(d) { return STATUS_OPACITY[d.status] || 1; }
  function entryUrl(d) { return '/projects/' + d.project + '/' + d.id; }

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
      return '<li class="health-item"><a href="' + entryUrl(e) + '">' +
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
                 (n.type === 'note' && showNotes);
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
      clusterY[p] = H * (0.1 + 0.8 * (Math.floor(i / cols + 0.5) / rows));
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

    // Edges
    var link = g.append('g')
      .selectAll('line')
      .data(linkData)
      .join('line')
      .attr('stroke', '#2a2a2a')
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
      .style('cursor', 'pointer')
      .on('mouseover', function (event, d) {
        tooltip.style.display = 'block';
        tooltip.innerHTML =
          '<strong>' + escHtml(d.title) + '</strong><br>' +
          escHtml(d.project) + ' · ' + d.type + ' · ' + d.status;
      })
      .on('mousemove', function (event) {
        var rect = wrap.getBoundingClientRect();
        tooltip.style.left = (event.clientX - rect.left + 14) + 'px';
        tooltip.style.top  = (event.clientY - rect.top  + 14) + 'px';
      })
      .on('mouseout', function () { tooltip.style.display = 'none'; })
      .on('click', function (event, d) { window.location.href = entryUrl(d); })
      .call(
        d3.drag()
          .on('start', function (event, d) {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
          })
          .on('drag', function (event, d) { d.fx = event.x; d.fy = event.y; })
          .on('end', function (event, d) {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null; d.fy = null;
          })
      );

    simulation.on('tick', function () {
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
      var data = await res.json();
      allNodes = data.nodes;
      allLinks = data.links;

      if (loadingEl) loadingEl.style.display = 'none';

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
