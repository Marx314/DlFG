import logging
import json
from datetime import date
from typing import List, Dict, Optional, Tuple
from models import NormalizedDataset, Developer, TrainingRecord, InvitationBatch
from normalize import get_status

logger = logging.getLogger(__name__)


class ReportGenerator:

    def __init__(self, dataset: NormalizedDataset):
        self.dataset = dataset
        self.metrics = {}
        self._index_data()

    def _index_data(self):
        self.developers_by_id = {d.id: d for d in self.dataset.developers}
        self.batches_by_id = {b.id: b for b in self.dataset.invitation_batches}
        self.records_by_dev_id = {}

        for record in self.dataset.training_records:
            dev_id = record.developer_id
            if dev_id not in self.records_by_dev_id:
                self.records_by_dev_id[dev_id] = []
            self.records_by_dev_id[dev_id].append(record)

    def generate_html(self) -> str:
        self._calculate_metrics()
        table_data = self._build_table_data()
        vp_breakdown = self._build_vp_breakdown()
        return self._assemble_html(table_data, vp_breakdown)

    def _assemble_html(self, table_data: Dict, vp_breakdown: Dict) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Training Compliance Report</title>
    <style>
{self._get_inline_css()}
    </style>
</head>
<body>
    <div class="container">
        {self._build_header()}
        {self._build_metrics_section()}
        {self._build_vp_section()}
        {self._build_comparison_section()}
        {self._build_needs_attention_section()}
        {self._build_table_section()}
    </div>
    <script>
        const TABLE_DATA = {json.dumps(table_data, default=str)};
        const VP_BREAKDOWN_DATA = {json.dumps(vp_breakdown, default=str)};
{self._get_inline_js()}
    </script>
</body>
</html>"""

    def _build_header(self) -> str:
        return f"""<header class="report-header">
            <h1>Training Compliance Report</h1>
            <p class="report-meta"><strong>{self._training_name()}</strong> • Generated: {date.today().isoformat()}</p>
        </header>"""

    def _build_metrics_section(self) -> str:
        m = self.metrics
        return f"""<section class="metrics-section">
            <div class="metrics-grid">
                <div class="metric-card"><div class="metric-value">{m['completion_rate']:.1f}%</div><div class="metric-label">Completion Rate</div><div class="metric-details">{m['completed']} completed</div></div>
                <div class="metric-card"><div class="metric-value">{m['overdue']}</div><div class="metric-label">Overdue</div><div class="metric-details">Not completed</div></div>
                <div class="metric-card"><div class="metric-value">{m['pending']}</div><div class="metric-label">Pending</div><div class="metric-details">Not yet due</div></div>
                <div class="metric-card"><div class="metric-value">{m['exempt']}</div><div class="metric-label">Exempt</div><div class="metric-details">Active exemptions</div></div>
                <div class="metric-card"><div class="metric-value">{m['departed']}</div><div class="metric-label">Departed</div><div class="metric-details">No longer active</div></div>
            </div>
        </section>"""

    def _build_vp_section(self) -> str:
        return """<section class="vp-breakdown-section">
            <h2>Completion by VP Organization</h2>
            <div id="vp-breakdown" class="vp-breakdown"></div>
        </section>"""

    def _build_comparison_section(self) -> str:
        rate = self.metrics['completion_rate']
        return f"""<section class="comparison-section">
            <h2>Comparison</h2>
            <div class="comparison-grid">
                <div class="comparison-card"><div class="comparison-label">Selected Org</div><div class="comparison-rate" id="selected-rate">--%</div></div>
                <div class="comparison-card"><div class="comparison-label">Company Overall</div><div class="comparison-rate" id="company-rate">{rate:.1f}%</div></div>
            </div>
        </section>"""

    def _build_needs_attention_section(self) -> str:
        return """<section class="needs-attention-section">
            <h2>Needs Attention</h2>
            <div id="needs-attention" class="needs-attention-list"></div>
        </section>"""

    def _build_table_section(self) -> str:
        return """<section class="table-section">
            <div class="table-tabs">
                <button class="tab-button active" data-tab="active">Active Developers</button>
                <button class="tab-button" data-tab="departed">Departed This Cycle</button>
            </div>
            <div class="tab-content active" id="active-tab"><div id="active-table-container" class="table-container"></div></div>
            <div class="tab-content" id="departed-tab"><div id="departed-table-container" class="table-container"></div></div>
        </section>"""

    def _training_name(self) -> str:
        if self.dataset.trainings:
            t = self.dataset.trainings[0]
            return f"{t.name} ({t.training_year})"
        return "Training Compliance Report"

    def _calculate_metrics(self):
        counts = {'completed': 0, 'overdue': 0, 'pending': 0, 'exempt': 0, 'departed': 0}
        for dev in self.dataset.developers:
            self._count_developer_status(dev, counts)
        non_exempt = self._count_non_exempt_active()
        completion_rate = 100.0 * counts['completed'] / non_exempt if non_exempt > 0 else 0.0
        self.metrics = {**counts, 'completion_rate': completion_rate, 'total_active': sum(1 for d in self.dataset.developers if d.is_active)}

    def _count_developer_status(self, dev: Developer, counts: Dict):
        if not dev.is_active:
            counts['departed'] += 1
        elif dev.exemption_start and not dev.exemption_end:
            counts['exempt'] += 1
        else:
            for record in self.dataset.training_records:
                if record.developer_id == dev.id:
                    self._count_record_status(record, counts)
                    break

    def _count_record_status(self, record: TrainingRecord, counts: Dict):
        if record.completed:
            counts['completed'] += 1
        else:
            batch = self.batches_by_id.get(record.invitation_batch_id)
            if batch and batch.due_date < date.today():
                counts['overdue'] += 1
            else:
                counts['pending'] += 1

    def _count_non_exempt_active(self) -> int:
        return sum(1 for d in self.dataset.developers if d.is_active and (not d.exemption_start or d.exemption_end))

    def _build_table_data(self) -> Dict:
        active, departed = [], []
        for dev in self.dataset.developers:
            row = self._build_developer_row(dev)
            (active if dev.is_active else departed).append(row)
        return {'active': active, 'departed': departed}

    def _build_developer_row(self, dev: Developer) -> Dict:
        row = {'name': dev.full_name, 'email': dev.email, 'id': dev.id, 'is_active': dev.is_active}
        self._add_org_info(row, dev.id)
        self._add_batch_records(row, dev)
        if not dev.is_active:
            row['left_on'] = dev.left_on.isoformat() if dev.left_on else None
        return row

    def _add_org_info(self, row: Dict, dev_id: str):
        orgs = [o for o in self.dataset.org_history if o.developer_id == dev_id]
        if orgs:
            orgs.sort(key=lambda o: o.effective_from, reverse=True)
            row['director'] = orgs[0].director or ''
            row['vp'] = orgs[0].vp or ''
        else:
            row['director'] = row['vp'] = ''

    def _add_batch_records(self, row: Dict, dev: Developer):
        records = self.records_by_dev_id.get(dev.id, [])
        batches = []
        for record in records:
            batch = self.batches_by_id.get(record.invitation_batch_id)
            if batch:
                batches.append({
                    'batch_code': batch.batch_code,
                    'due_date': batch.due_date.isoformat(),
                    'status': get_status(dev, record, batch),
                    'completion_date': record.completion_date.isoformat() if record.completion_date else None,
                    'attempts': record.attempts,
                })
        row['batches'] = batches

    def _build_vp_breakdown(self) -> Dict:
        vp_dirs = self._group_devs_by_vp_director()
        vps = [self._build_vp_data(vp, dirs) for vp, dirs in sorted(vp_dirs.items())]
        return {'vps': vps}

    def _group_devs_by_vp_director(self) -> Dict:
        groups = {}
        for dev in self.dataset.developers:
            if not dev.is_active:
                continue
            orgs = [o for o in self.dataset.org_history if o.developer_id == dev.id]
            if not orgs:
                continue
            orgs.sort(key=lambda o: o.effective_from, reverse=True)
            org = orgs[0]
            vp = org.vp or 'Unassigned'
            director = org.director or 'Unassigned'
            if vp not in groups:
                groups[vp] = {}
            if director not in groups[vp]:
                groups[vp][director] = []
            groups[vp][director].append(dev.id)
        return groups

    def _build_vp_data(self, vp: str, dirs_dict: Dict) -> Dict:
        all_devs = [d for devs in dirs_dict.values() for d in devs]
        vp_completed = sum(1 for d in all_devs if any(r.completed for r in self.records_by_dev_id.get(d, [])))
        vp_total = len(all_devs)
        return {
            'name': vp,
            'total': vp_total,
            'completed': vp_completed,
            'rate': 100.0 * vp_completed / vp_total if vp_total > 0 else 0.0,
            'directors': [self._build_director_data(d, ids) for d, ids in sorted(dirs_dict.items())],
        }

    def _build_director_data(self, director: str, dev_ids: List[str]) -> Dict:
        completed = sum(1 for d in dev_ids if any(r.completed for r in self.records_by_dev_id.get(d, [])))
        total = len(dev_ids)
        return {
            'name': director,
            'total': total,
            'completed': completed,
            'rate': 100.0 * completed / total if total > 0 else 0.0,
        }

    @staticmethod
    def _get_inline_css() -> str:
        return """
        * { margin: 0; padding: 0; box-sizing: border-box; }

        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', sans-serif;
            background-color: #f5f7fa;
            color: #333;
            line-height: 1.6;
        }

        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }

        .report-header {
            background: white;
            padding: 30px 20px;
            border-bottom: 2px solid #e0e3e8;
            margin-bottom: 30px;
        }

        .report-header h1 { font-size: 28px; font-weight: 600; margin-bottom: 10px; }

        .report-meta {
            font-size: 13px;
            color: #666;
        }

        .metrics-section { margin-bottom: 40px; }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 15px;
        }

        .metric-card {
            background: white;
            padding: 20px;
            border: 1px solid #e0e3e8;
            border-radius: 6px;
            text-align: center;
        }

        .metric-value {
            font-size: 28px;
            font-weight: 700;
            margin-bottom: 5px;
            color: #1a73e8;
        }

        .metric-label { font-weight: 600; font-size: 13px; color: #666; margin-bottom: 5px; }

        .metric-details { font-size: 12px; color: #999; }

        .vp-breakdown-section, .comparison-section, .needs-attention-section, .table-section {
            background: white;
            padding: 25px;
            border: 1px solid #e0e3e8;
            border-radius: 6px;
            margin-bottom: 25px;
        }

        h2 { font-size: 18px; font-weight: 600; margin-bottom: 20px; color: #1a1a1a; }

        .vp-breakdown {
            border-left: 3px solid #1a73e8;
            padding-left: 20px;
        }

        .vp-row {
            margin-bottom: 25px;
        }

        .vp-header {
            cursor: pointer;
            padding: 12px;
            background: #f8f9fa;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            user-select: none;
        }

        .vp-header:hover { background: #e8eaed; }

        .vp-name { font-weight: 600; }

        .vp-rate {
            font-weight: 700;
            color: #1a73e8;
        }

        .vp-directors {
            margin-top: 10px;
            display: none;
            padding-left: 20px;
            border-left: 2px solid #dadce0;
        }

        .vp-row.expanded .vp-directors { display: block; }

        .director-row {
            padding: 8px 0;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 14px;
        }

        .comparison-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
        }

        .comparison-card {
            padding: 20px;
            background: #f8f9fa;
            border-radius: 6px;
            text-align: center;
        }

        .comparison-label { font-size: 12px; color: #666; text-transform: uppercase; margin-bottom: 10px; }

        .comparison-rate { font-size: 32px; font-weight: 700; color: #1a73e8; }

        .needs-attention-list {
            border-left: 3px solid #fbbc04;
            padding-left: 20px;
        }

        .attention-item {
            padding: 12px;
            margin-bottom: 10px;
            background: #fffbea;
            border-radius: 4px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .attention-item-name { font-weight: 600; }

        .attention-item-details { font-size: 13px; color: #666; margin-top: 4px; }

        .status-badge {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            white-space: nowrap;
        }

        .status-completed { background: #d4edda; color: #155724; }
        .status-overdue { background: #f8d7da; color: #721c24; }
        .status-pending { background: #fff3cd; color: #856404; }
        .status-exempt { background: #e2e3e5; color: #383d41; }
        .status-departed { background: #e2e3e5; color: #383d41; }

        .table-tabs {
            display: flex;
            border-bottom: 2px solid #e0e3e8;
            margin-bottom: 20px;
            gap: 10px;
        }

        .tab-button {
            padding: 12px 20px;
            background: none;
            border: none;
            border-bottom: 3px solid transparent;
            cursor: pointer;
            font-size: 14px;
            font-weight: 600;
            color: #666;
            transition: all 0.2s;
        }

        .tab-button.active {
            color: #1a73e8;
            border-bottom-color: #1a73e8;
        }

        .tab-content { display: none; }
        .tab-content.active { display: block; }

        .table-container { overflow-x: auto; }

        table {
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }

        th {
            background: #f8f9fa;
            padding: 12px;
            text-align: left;
            font-weight: 600;
            border-bottom: 2px solid #e0e3e8;
            cursor: pointer;
            user-select: none;
            white-space: nowrap;
        }

        th:hover { background: #e8eaed; }

        th.sortable::after { content: ' ⇅'; color: #999; }

        td {
            padding: 12px;
            border-bottom: 1px solid #e0e3e8;
        }

        tr:hover { background: #f8f9fa; }

        @media print {
            body { background: white; }
            .report-header { border-bottom: 3px solid #333; }
            .metric-card, .vp-breakdown-section, .comparison-section, .needs-attention-section, .table-section {
                page-break-inside: avoid;
            }
        }
"""

    @staticmethod
    def _get_inline_js() -> str:
        return """
        function renderVPBreakdown() {
            const container = document.getElementById('vp-breakdown');
            container.innerHTML = '';

            VP_BREAKDOWN_DATA.vps.forEach(vp => {
                const vpRow = document.createElement('div');
                vpRow.className = 'vp-row';
                vpRow.innerHTML = `
                    <div class="vp-header">
                        <span>
                            <span class="vp-name">${vp.name}</span>
                            <span style="margin-left: 20px; color: #999; font-size: 13px;">
                                ${vp.completed} / ${vp.total}
                            </span>
                        </span>
                        <span class="vp-rate">${vp.rate.toFixed(1)}%</span>
                    </div>
                    <div class="vp-directors"></div>
                `;

                const directorsContainer = vpRow.querySelector('.vp-directors');
                vp.directors.forEach(dir => {
                    const dirRow = document.createElement('div');
                    dirRow.className = 'director-row';
                    dirRow.innerHTML = `
                        <span>${dir.name} <span style="color: #999; font-size: 12px;">${dir.completed}/${dir.total}</span></span>
                        <span style="font-weight: 700; color: #1a73e8;">${dir.rate.toFixed(1)}%</span>
                    `;
                    directorsContainer.appendChild(dirRow);
                });

                vpRow.querySelector('.vp-header').addEventListener('click', () => {
                    vpRow.classList.toggle('expanded');
                });

                container.appendChild(vpRow);
            });
        }

        function renderTable(tabName) {
            const data = TABLE_DATA[tabName] || [];
            const container = document.getElementById(tabName === 'active' ? 'active-table-container' : 'departed-table-container');

            const table = document.createElement('table');
            table.dataset.currentSort = 'name';
            table.dataset.sortAsc = true;

            const thead = document.createElement('thead');
            const headerRow = document.createElement('tr');
            const headers = ['Name', 'Email', 'Director', 'Batch', 'Due Date', 'Status', 'Completion Date', 'Attempts'];

            if (tabName === 'departed') {
                headers.push('Left On');
            }

            headers.forEach(h => {
                const th = document.createElement('th');
                th.textContent = h;
                th.className = 'sortable';
                headerRow.appendChild(th);
            });

            thead.appendChild(headerRow);
            table.appendChild(thead);

            const tbody = document.createElement('tbody');
            data.forEach(row => {
                const batch = row.batches[0] || {};
                const status = batch.status || 'pending';

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${row.name}</td>
                    <td style="font-size: 12px; color: #666;">${row.email}</td>
                    <td>${row.director || '–'}</td>
                    <td>${batch.batch_code || '–'}</td>
                    <td>${batch.due_date || '–'}</td>
                    <td><span class="status-badge status-${status}">${status}</span></td>
                    <td>${batch.completion_date || '–'}</td>
                    <td>${batch.attempts || 0}</td>
                    ${tabName === 'departed' ? `<td>${row.left_on || '–'}</td>` : ''}
                `;
                tbody.appendChild(tr);
            });

            table.appendChild(tbody);
            container.innerHTML = '';
            container.appendChild(table);

            thead.querySelectorAll('th').forEach((th, idx) => {
                th.addEventListener('click', () => {
                    sortTable(table, tbody, idx, headers[idx].toLowerCase().replace(' ', '_'));
                });
            });
        }

        function sortTable(table, tbody, colIdx, colName) {
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const isAsc = table.dataset.sortAsc === 'true';
            const shouldAsc = table.dataset.currentSort === colName ? !isAsc : true;

            rows.sort((a, b) => {
                const aVal = a.cells[colIdx].textContent.trim();
                const bVal = b.cells[colIdx].textContent.trim();
                const cmp = aVal < bVal ? -1 : (aVal > bVal ? 1 : 0);
                return shouldAsc ? cmp : -cmp;
            });

            rows.forEach(r => tbody.appendChild(r));
            table.dataset.currentSort = colName;
            table.dataset.sortAsc = shouldAsc;
        }

        function setupTabs() {
            document.querySelectorAll('.tab-button').forEach(btn => {
                btn.addEventListener('click', () => {
                    const tabName = btn.dataset.tab;
                    document.querySelectorAll('.tab-button').forEach(b => b.classList.remove('active'));
                    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                    btn.classList.add('active');
                    document.getElementById(tabName + '-tab').classList.add('active');
                    renderTable(tabName);
                });
            });
        }

        document.addEventListener('DOMContentLoaded', () => {
            renderVPBreakdown();
            renderTable('active');
            setupTabs();
        });
"""
