#!/usr/bin/env python3
"""Ferramenta local para percorrer uma location e recortar os seus Souvenirs.

Lê a fila na Base44, mas não escreve na API nem nas imagens canónicas.
"""

from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
import mimetypes
import os
import re
import sys
import unicodedata
import uuid
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "recortes_souvenir_teste"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sync_catalog_images_api import direct_download, unique_record_slugs  # noqa: E402
from scripts.sync_coin_images_api import (  # noqa: E402
    API_KEY_ENV,
    DEFAULT_RAW_BASE_URL,
    api_request,
    load_dotenv,
)



PAGE = r"""<!doctype html>
<html lang="pt">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Recortador de Souvenirs</title>
  <style>
    :root { color-scheme: light; font-family: Inter, system-ui, sans-serif; }
    body { margin: 0; background: #f4f1eb; color: #27221d; }
    main { max-width: 1180px; margin: 0 auto; padding: 24px; }
    h1 { margin: 0 0 6px; font-size: 28px; }
    .hint { color: #71685e; margin: 0 0 18px; }
    .layout { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 18px; }
    .panel { background: white; border: 1px solid #ded7ce; border-radius: 14px; padding: 16px; box-shadow: 0 3px 16px #4a392214; }
    .photo-progress { display: flex; justify-content: space-between; gap: 14px; align-items: center; margin-bottom: 12px; padding: 11px 12px; border: 1px solid #dfd5ca; border-radius: 10px; background: #f5f1ec; }
    .photo-progress strong, .photo-progress small { display: block; }
    .photo-progress small { margin-top: 2px; color: #6e655c; }
    .photo-progress button { width: auto; margin: 0; white-space: nowrap; }
    .photo-progress.ready { border-color: #e3aa75; background: #fff4e9; }
    .photo-progress.complete { border-color: #91c6a0; background: #edf8f0; }
    #drop { min-height: 420px; display: grid; place-items: center; border: 2px dashed #c6b9aa; border-radius: 10px; overflow: auto; background: #fbfaf8; position: relative; }
    #drop.active { border-color: #c16b21; background: #fff7ef; }
    #empty { padding: 40px; text-align: center; color: #756a60; }
    canvas { display: none; max-width: 100%; height: auto; cursor: crosshair; touch-action: none; }
    label { display: block; margin: 13px 0 5px; font-size: 13px; color: #665c53; }
    input, select, button { box-sizing: border-box; width: 100%; border-radius: 8px; border: 1px solid #cfc6bc; padding: 10px 11px; font: inherit; }
    button { border: 0; background: #b95f18; color: white; font-weight: 650; cursor: pointer; margin-top: 13px; }
    button:disabled { background: #b8afa7; cursor: default; }
    .secondary { background: #e9e4de; color: #3d352e; }
    .status { margin-top: 14px; padding: 10px; border-radius: 8px; background: #f4f1ed; font-size: 13px; white-space: pre-wrap; }
    .saved { margin-top: 16px; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
    .coin-card { display: grid; grid-template-columns: 82px minmax(0, 1fr); gap: 12px; align-items: center; min-height: 82px; padding: 10px; border: 2px solid #e9e2da; border-radius: 10px; background: #fff; cursor: pointer; }
    .coin-card:hover { border-color: #d59a69; background: #fffaf5; }
    .coin-card.active { border-color: #b95f18; background: #fff5eb; box-shadow: 0 0 0 2px #b95f1820; }
    .coin-card.prepared .coin-state { color: #2f7a45; }
    .coin-thumb { display: grid; place-items: center; width: 82px; height: 64px; object-fit: contain; background: #f4f2ef; border-radius: 7px; color: #8a7f75; font-weight: 700; }
    .coin-card strong, .coin-card small { display: block; overflow-wrap: anywhere; }
    .coin-card small { margin-top: 4px; color: #6e655c; }
    .check { display: flex; gap: 8px; align-items: flex-start; margin-top: 13px; font-size: 13px; color: #554c44; }
    .check input { width: auto; margin-top: 2px; }
    .assignment { border: 1px solid #e4b88f; background: #fff5eb; }
    .assignment strong { display: block; font-size: 16px; color: #8d430e; margin-bottom: 4px; }
    .assignment small { color: #6e6258; }
    @media (max-width: 800px) { .layout { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
<main>
  <h1>Recortador de Souvenirs</h1>
  <p class="hint">Escolhe uma location e recorta a moeda indicada. Também podes colar outra montagem com Ctrl+V.</p>
  <div class="layout">
    <section class="panel">
      <div id="photo-progress" class="photo-progress">
        <div><strong id="photo-state">Escolhe uma fotografia</strong><small id="photo-count">Sem progresso para mostrar.</small></div>
        <button id="complete-photo" disabled>Marcar fotografia como feita</button>
      </div>
      <div id="drop">
        <div id="empty">Clica aqui e cola a imagem<br><strong>Ctrl+V</strong><br><br>ou usa “Escolher imagem”</div>
        <canvas id="canvas"></canvas>
      </div>
      <input id="file" type="file" accept="image/*" hidden>
      <button id="choose" class="secondary">Escolher imagem</button>
      <div id="status" class="status">Os ficheiros guardados aparecerão aqui.</div>
      <div id="saved" class="saved"></div>
    </section>
    <aside class="panel">
      <label for="location">Location</label>
      <select id="location">
        <option value="">A carregar locations…</option>
      </select>
      <label for="machine">Fotografia / máquina</label>
      <select id="machine" disabled>
        <option value="">Escolhe primeiro uma location</option>
      </select>
      <div id="assignment" class="status assignment">Escolhe uma location para começar.</div>
      <hr>
      <strong>Recorte selecionado</strong>
      <div id="coords" class="status">Ainda não selecionaste uma moeda.</div>
      <label for="orientation">Formato final</label>
      <select id="orientation">
        <option value="landscape">Deitada — 200 × 115 px</option>
        <option value="portrait">Em pé — 80 × 140 px</option>
      </select>
      <label for="padding">Margem adicional (px)</label>
      <input id="padding" type="number" min="0" max="100" value="4">
      <label class="check"><input id="cleanup" type="checkbox" checked><span>Limpar resíduos das bordas e centrar a moeda no recorte</span></label>
      <button id="save" disabled>Guardar recorte</button>
      <button id="clear" class="secondary" disabled>Limpar seleção</button>
    </aside>
  </div>
</main>
<script>
const canvas = document.querySelector('#canvas');
const ctx = canvas.getContext('2d');
const drop = document.querySelector('#drop');
const empty = document.querySelector('#empty');
const fileInput = document.querySelector('#file');
const saveButton = document.querySelector('#save');
const clearButton = document.querySelector('#clear');
const coords = document.querySelector('#coords');
const statusBox = document.querySelector('#status');
const machineInput = document.querySelector('#machine');
const paddingInput = document.querySelector('#padding');
const orientationInput = document.querySelector('#orientation');
const cleanupInput = document.querySelector('#cleanup');
const saved = document.querySelector('#saved');
const locationInput = document.querySelector('#location');
const assignment = document.querySelector('#assignment');
const photoProgress = document.querySelector('#photo-progress');
const photoState = document.querySelector('#photo-state');
const photoCount = document.querySelector('#photo-count');
const completePhotoButton = document.querySelector('#complete-photo');
let records = [];
let currentRecord = null;
let currentIndex = -1;

let image = new Image();
let currentMachine = null;
let imageBlob = null;
let sourceId = null;
let selection = null;
let start = null;

function targetSize() {
  return orientationInput.value === 'portrait' ? {width:80, height:140} : {width:200, height:115};
}

function fixedSelection(origin, current) {
  const target = targetSize();
  const ratio = target.width / target.height;
  const signX = current.x >= origin.x ? 1 : -1;
  const signY = current.y >= origin.y ? 1 : -1;
  let width = Math.abs(current.x - origin.x);
  let height = Math.abs(current.y - origin.y);
  if (height === 0 || width / height > ratio) height = width / ratio;
  else width = height * ratio;
  width = Math.min(width, signX > 0 ? canvas.width - origin.x : origin.x);
  height = width / ratio;
  if (height > (signY > 0 ? canvas.height - origin.y : origin.y)) {
    height = signY > 0 ? canvas.height - origin.y : origin.y;
    width = height * ratio;
  }
  return {
    x: signX > 0 ? origin.x : origin.x - width,
    y: signY > 0 ? origin.y : origin.y - height,
    width, height
  };
}

function point(event) {
  const box = canvas.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(canvas.width, (event.clientX - box.left) * canvas.width / box.width)),
    y: Math.max(0, Math.min(canvas.height, (event.clientY - box.top) * canvas.height / box.height))
  };
}

function draw() {
  if (!image.complete || !image.naturalWidth) return;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(image, 0, 0);
  if (selection) {
    ctx.save();
    ctx.fillStyle = 'rgba(0,0,0,.38)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.clearRect(selection.x, selection.y, selection.width, selection.height);
    ctx.drawImage(image, selection.x, selection.y, selection.width, selection.height,
      selection.x, selection.y, selection.width, selection.height);
    ctx.strokeStyle = '#ff6a00';
    ctx.lineWidth = Math.max(2, canvas.width / 350);
    ctx.strokeRect(selection.x, selection.y, selection.width, selection.height);
    ctx.restore();
  }
}

function updateSelection() {
  const valid = selection && selection.width >= 5 && selection.height >= 5;
  saveButton.disabled = !valid || !sourceId;
  clearButton.disabled = !selection;
  coords.textContent = valid
    ? `x=${Math.round(selection.x)}, y=${Math.round(selection.y)}\nSeleção: ${Math.round(selection.width)} × ${Math.round(selection.height)} px\nSaída: ${targetSize().width} × ${targetSize().height} px`
    : 'Ainda não selecionaste uma moeda.';
}

async function loadBlob(blob, suggestedName='') {
  if (!blob || !blob.type.startsWith('image/')) {
    statusBox.textContent = 'O conteúdo colado não é uma imagem.';
    return;
  }
  imageBlob = blob;
  statusBox.textContent = 'A carregar imagem…';
  const response = await fetch('/api/source', {method: 'POST', headers: {'Content-Type': blob.type}, body: blob});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Falha ao guardar a imagem original.');
  sourceId = result.source_id;
  image = new Image();
  image.onload = () => {
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    canvas.style.display = 'block';
    empty.style.display = 'none';
    selection = null;
    draw();
    updateSelection();
    statusBox.textContent = `Original guardado em:\n${result.path}`;
  };
  image.src = URL.createObjectURL(blob);
}

function recordsForMachine(machine) {
  return records.filter(record => record.machine === Number(machine));
}

function machineLabel(machine) {
  const items = recordsForMachine(machine);
  const prepared = items.filter(record => record.prepared).length;
  const completed = items.length > 0 && items.every(record => record.photo_completed);
  return `Máquina ${machine} · ${prepared}/${items.length} recortes${completed ? ' · completa' : ''}`;
}

function updatePhotoProgress() {
  const items = recordsForMachine(currentMachine);
  if (!items.length) {
    photoProgress.className = 'photo-progress';
    photoState.textContent = 'Escolhe uma fotografia';
    photoCount.textContent = 'Sem progresso para mostrar.';
    completePhotoButton.disabled = true;
    return;
  }
  const prepared = items.filter(record => record.prepared).length;
  const completed = items.every(record => record.photo_completed);
  photoCount.textContent = `${prepared}/${items.length} recortes preparados · Máquina ${currentMachine}`;
  if (completed) {
    photoProgress.className = 'photo-progress complete';
    photoState.textContent = 'Fotografia completa';
    completePhotoButton.textContent = 'Remover conclusão';
    completePhotoButton.className = 'secondary';
    completePhotoButton.disabled = false;
  } else if (prepared === items.length) {
    photoProgress.className = 'photo-progress ready';
    photoState.textContent = 'Pronta para confirmar';
    completePhotoButton.textContent = 'Marcar fotografia como feita';
    completePhotoButton.className = '';
    completePhotoButton.disabled = false;
  } else {
    photoProgress.className = 'photo-progress';
    photoState.textContent = 'Fotografia por completar';
    completePhotoButton.textContent = 'Marcar fotografia como feita';
    completePhotoButton.className = '';
    completePhotoButton.disabled = true;
  }
}

function updateMachineOption(machine) {
  const option = [...machineInput.options].find(item => item.value === String(machine));
  if (option) option.textContent = machineLabel(machine);
}

function renderMachineGallery() {
  saved.innerHTML = '';
  recordsForMachine(currentMachine)
    .sort((left, right) => left.position - right.position)
    .forEach(record => {
      const index = records.findIndex(candidate => candidate.id === record.id);
      const article = document.createElement('article');
      article.className = `coin-card${record.prepared ? ' prepared' : ''}${currentRecord && currentRecord.id === record.id ? ' active' : ''}`;
      article.tabIndex = 0;
      article.setAttribute('role', 'button');
      article.setAttribute('aria-label', `Selecionar posição ${record.position}: ${record.name}`);
      const thumbnail = document.createElement(record.prepared && record.output_url ? 'img' : 'span');
      thumbnail.className = 'coin-thumb';
      if (record.prepared && record.output_url) {
        thumbnail.src = `${record.output_url}?v=${Date.now()}`;
        thumbnail.alt = '';
      } else {
        thumbnail.textContent = record.position;
      }
      const details = document.createElement('div');
      const name = document.createElement('strong');
      name.textContent = record.name;
      const state = document.createElement('small');
      state.className = 'coin-state';
      const orientation = record.orientation === 'portrait' ? 'Em pé' : 'Deitada';
      state.textContent = `Posição ${record.position} · ${orientation} · ${record.prepared ? 'Preparado' : 'Por recortar'}`;
      details.append(name, state);
      article.append(thumbnail, details);
      article.onclick = () => selectRecord(index).catch(showError);
      article.onkeydown = event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          selectRecord(index).catch(showError);
        }
      };
      saved.appendChild(article);
    });
}

function displayRecordImage(blob, sourceResult) {
  sourceId = sourceResult.source_id;
  image = new Image();
  image.onload = () => {
    canvas.width = image.naturalWidth;
    canvas.height = image.naturalHeight;
    canvas.style.display = 'block';
    empty.style.display = 'none';
    selection = null;
    draw();
    updateSelection();
    statusBox.textContent = 'Fotografia da máquina carregada. Seleciona a moeda indicada.';
  };
  image.src = URL.createObjectURL(blob);
}

async function selectRecord(index) {
  if (index < 0 || index >= records.length) return;
  currentIndex = index;
  currentRecord = records[index];
  currentMachine = currentRecord.machine;
  orientationInput.value = currentRecord.orientation;
  selection = null;
  draw();
  updateSelection();
  renderMachineGallery();
  const machineItems = recordsForMachine(currentMachine);
  const numberInMachine = machineItems.findIndex(record => record.id === currentRecord.id) + 1;
  assignment.textContent =
    `Recorta esta moeda:\n${currentRecord.name}\nMáquina ${currentRecord.machine} · Posição ${currentRecord.position}\n` +
    `Nesta fotografia: ${numberInMachine}/${machineItems.length}`;
  statusBox.textContent = 'A carregar a fotografia desta máquina…';
  const response = await fetch(`/api/record-source/${currentRecord.id}`);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Não foi possível carregar a fotografia da máquina.');
  if (sourceId === result.source_id && image.complete && image.naturalWidth) {
    statusBox.textContent = 'Fotografia da máquina carregada. Seleciona a moeda indicada.';
    return;
  }
  const imageResponse = await fetch(result.url);
  if (!imageResponse.ok) throw new Error('Não foi possível abrir a fotografia preparada.');
  displayRecordImage(await imageResponse.blob(), result);
}

async function selectMachine(machine) {
  currentMachine = Number(machine);
  const items = recordsForMachine(currentMachine);
  renderMachineGallery();
  updatePhotoProgress();
  const firstPending = items.find(record => !record.prepared) || items[0];
  if (firstPending) {
    await selectRecord(records.findIndex(record => record.id === firstPending.id));
  }
}

async function loadLocation(locationId) {
  if (!locationId) {
    records = [];
    currentRecord = null;
    currentIndex = -1;
    currentMachine = null;
    machineInput.disabled = true;
    saved.innerHTML = '';
    assignment.textContent = 'Escolhe uma location para começar.';
    updatePhotoProgress();
    return;
  }
  assignment.textContent = 'A carregar as moedas desta location…';
  const response = await fetch(`/api/location-records?location=${encodeURIComponent(locationId)}`);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Não foi possível carregar a location.');
  records = result.records || [];
  const machines = [...new Set(records.map(record => record.machine))].sort((left, right) => left - right);
  machineInput.innerHTML = '';
  machines.forEach(machine => {
    const option = document.createElement('option');
    option.value = String(machine);
    option.textContent = machineLabel(machine);
    machineInput.appendChild(option);
  });
  machineInput.disabled = machines.length === 0;
  if (!machines.length) {
    assignment.textContent = 'Esta location não tem moedas externas pendentes.';
    saved.innerHTML = '';
    updatePhotoProgress();
    return;
  }
  const firstPending = records.find(record => !record.prepared);
  const firstMachine = firstPending ? firstPending.machine : machines[0];
  machineInput.value = String(firstMachine);
  await selectMachine(firstMachine);
}

async function loadLocations() {
  const response = await fetch('/api/locations');
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Não foi possível consultar as locations.');
  locationInput.innerHTML = '<option value="">Escolhe uma location…</option>';
  (result.locations || []).forEach(location => {
    const option = document.createElement('option');
    option.value = location.id;
    option.textContent =
      `${location.name} · location ${location.id} · ${location.count} moedas / ${location.machines} montagens`;
    locationInput.appendChild(option);
  });
  if ((result.locations || []).length === 1) {
    locationInput.value = result.locations[0].id;
    await loadLocation(locationInput.value);
  }
}

function advanceQueue() {
  if (!currentRecord) return;
  currentRecord.prepared = true;
  updateMachineOption(currentMachine);
  renderMachineGallery();
  updatePhotoProgress();
  const items = recordsForMachine(currentMachine);
  const next = items.find(record => !record.prepared);
  if (next) {
    selectRecord(records.findIndex(record => record.id === next.id)).catch(showError);
  } else {
    assignment.textContent = `Máquina ${currentMachine} concluída: ${items.length}/${items.length} recortes preparados.`;
    currentRecord = null;
    selection = null;
    renderMachineGallery();
    draw();
    updateSelection();
  }
}

locationInput.onchange = () => loadLocation(locationInput.value).catch(showError);
machineInput.onchange = () => selectMachine(machineInput.value).catch(showError);
completePhotoButton.onclick = async () => {
  const items = recordsForMachine(currentMachine);
  if (!items.length) return;
  const wasCompleted = items.every(record => record.photo_completed);
  const completed = !wasCompleted;
  if (completed && items.some(record => !record.prepared)) return;
  completePhotoButton.disabled = true;
  try {
    const response = await fetch('/api/photo-status', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
      location_id: locationInput.value, machine: currentMachine, completed
    })});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Não foi possível alterar o estado da fotografia.');
    items.forEach(record => { record.photo_completed = completed; });
    updateMachineOption(currentMachine);
    updatePhotoProgress();
    assignment.textContent = completed
      ? `Máquina ${currentMachine} confirmada como completa.`
      : `Máquina ${currentMachine} reaberta para revisão.`;
  } catch (error) { showError(error); updatePhotoProgress(); }
};

document.addEventListener('paste', event => {
  const item = [...event.clipboardData.items].find(value => value.type.startsWith('image/'));
  if (item) { event.preventDefault(); loadBlob(item.getAsFile()).catch(showError); }
});
document.querySelector('#choose').onclick = () => fileInput.click();
fileInput.onchange = () => fileInput.files[0] && loadBlob(fileInput.files[0], fileInput.files[0].name).catch(showError);
['dragenter', 'dragover'].forEach(type => drop.addEventListener(type, event => { event.preventDefault(); drop.classList.add('active'); }));
['dragleave', 'drop'].forEach(type => drop.addEventListener(type, event => { event.preventDefault(); drop.classList.remove('active'); }));
drop.addEventListener('drop', event => event.dataTransfer.files[0] && loadBlob(event.dataTransfer.files[0], event.dataTransfer.files[0].name).catch(showError));

canvas.addEventListener('pointerdown', event => { start = point(event); canvas.setPointerCapture(event.pointerId); selection = {x:start.x,y:start.y,width:0,height:0}; draw(); });
canvas.addEventListener('pointermove', event => {
  if (!start) return;
  const current = point(event);
  selection = fixedSelection(start, current);
  draw(); updateSelection();
});
canvas.addEventListener('pointerup', () => { start = null; updateSelection(); });
orientationInput.onchange = () => { selection = null; draw(); updateSelection(); };
clearButton.onclick = () => { selection = null; draw(); updateSelection(); };

saveButton.onclick = async () => {
  if (!selection || !sourceId) return;
  saveButton.disabled = true;
  statusBox.textContent = 'A guardar recorte…';
  try {
    const response = await fetch('/api/crop', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({
      source_id: sourceId, name: currentRecord ? currentRecord.slug : 'recorte', padding: Number(paddingInput.value || 0),
      record_id: currentRecord ? currentRecord.id : '',
      orientation: orientationInput.value, cleanup: cleanupInput.checked, ...selection
    })});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Falha ao guardar o recorte.');
    const cleanupText = result.cleaned ? ' · resíduos removidos' : '';
    const centeredText = result.centered ? ' · moeda centrada' : '';
    statusBox.textContent = `Guardado: ${result.width} × ${result.height} px (${result.orientation})${cleanupText}${centeredText}\n${result.path}`;
    if (currentRecord) {
      recordsForMachine(currentMachine).forEach(record => { record.photo_completed = false; });
      currentRecord.output_url = result.url;
      currentRecord.output_filename = result.filename;
      currentRecord.prepared = true;
      renderMachineGallery();
      updatePhotoProgress();
      setTimeout(advanceQueue, 700);
    }
  } catch (error) { showError(error); }
  updateSelection();
};

function showError(error) { statusBox.textContent = `Erro: ${error.message || error}`; }

loadLocations().catch(showError);

fetch('/api/bootstrap').then(response => response.json()).then(async result => {
  if (!result.url) return;
  const response = await fetch(result.url);
  await loadBlob(await response.blob(), result.name || '');
}).catch(showError);
</script>
</body>
</html>"""


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-") or "recorte"

def record_location_id(record: dict[str, object]) -> str:
    query = parse_qs(urlparse(str(record.get("reference_url") or "")).query)
    return str(query.get("location", ["sem-id"])[0])


def record_machine_position(record: dict[str, object]) -> tuple[int, int]:
    reference = str(record.get("reference_url") or "")
    match = re.search(r"#machine-(\d+)-position-(\d+)", reference, re.IGNORECASE)
    if not match:
        match = re.search(
            r"Machine\s+(\d+)\s*[·|-]\s*Posição\s+(\d+)",
            str(record.get("notes") or ""),
            re.IGNORECASE,
        )
    return (int(match.group(1)), int(match.group(2))) if match else (9999, int(record.get("ordem") or 9999))


def record_orientation(record: dict[str, object]) -> str:
    explicit = str(record.get("display_orientation") or "")
    if explicit in {"portrait", "landscape"}:
        return explicit
    notes = str(record.get("notes") or "").casefold()
    return "portrait" if "vertical" in notes else "landscape"


def load_pending_souvenirs() -> list[dict[str, object]]:
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        raise RuntimeError(f"Define {API_KEY_ENV} no ficheiro .env.")
    data = api_request(
        "GET",
        "/entities/Souvenir",
        api_key,
        query={"limit": 5000, "q": json.dumps({"type": "pressed"})},
    )
    if not isinstance(data, list):
        raise RuntimeError(f"Resposta inesperada ao listar Souvenirs: {data!r}")
    records = [row for row in data if isinstance(row, dict)]
    slugs = unique_record_slugs(records, "souvenir")
    pending: list[dict[str, object]] = []
    for record in records:
        source = str(record.get("image_front") or "")
        if not source or source.startswith(DEFAULT_RAW_BASE_URL):
            continue
        machine, position = record_machine_position(record)
        item = dict(record)
        item["_location_id"] = record_location_id(record)
        item["_machine"] = machine
        item["_position"] = position
        item["_orientation"] = record_orientation(record)
        item["_slug"] = slugs[str(record["id"])]
        pending.append(item)
    return sorted(
        pending,
        key=lambda item: (
            str(item.get("location_name") or "").casefold(),
            str(item["_location_id"]),
            int(item["_machine"]),
            int(item["_position"]),
            str(item.get("name") or "").casefold(),
        ),
    )


def read_manifest(output_dir: Path) -> dict[str, object]:
    path = output_dir / "manifest.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_manifest(output_dir: Path, record_id: str, entry: dict[str, object]) -> None:
    manifest = read_manifest(output_dir)
    manifest[record_id] = entry
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_photo_status(output_dir: Path) -> dict[str, object]:
    path = output_dir / "photo-status.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def photo_status_key(record: dict[str, object]) -> str:
    source_url = str(record.get("image_front") or "")
    source_hash = hashlib.sha256(source_url.encode()).hexdigest()[:12]
    return f"{record['_location_id']}:machine-{record['_machine']}:{source_hash}"


def set_photo_status(output_dir: Path, record: dict[str, object], completed: bool) -> None:
    statuses = read_photo_status(output_dir)
    key = photo_status_key(record)
    statuses[key] = {
        "completed": completed,
        "location_id": str(record["_location_id"]),
        "location_name": str(record.get("location_name") or ""),
        "machine": int(record["_machine"]),
        "source_url": str(record.get("image_front") or ""),
    }
    (output_dir / "photo-status.json").write_text(
        json.dumps(statuses, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def clean_isolated_edge_residue(image: Image.Image) -> tuple[Image.Image, bool, bool]:
    """Mantém o principal objeto central e remove componentes isolados do fundo.

    A seleção deve deixar fundo claro nos cantos. A máscara é ligeiramente
    fechada para unir detalhes da moeda antes de escolher o maior componente
    próximo do centro.
    """
    rgb = image.convert("RGB")
    border = [rgb.getpixel((x, 0)) for x in range(rgb.width)]
    border.extend(rgb.getpixel((x, rgb.height - 1)) for x in range(rgb.width))
    border.extend(rgb.getpixel((0, y)) for y in range(1, rgb.height - 1))
    border.extend(rgb.getpixel((rgb.width - 1, y)) for y in range(1, rgb.height - 1))
    brightest = sorted(border, key=sum, reverse=True)[: max(8, len(border) // 4)]
    background = tuple(
        sorted(pixel[channel] for pixel in brightest)[len(brightest) // 2]
        for channel in range(3)
    )
    difference = Image.new("L", rgb.size)
    rgb_pixels = rgb.load()
    difference.putdata(
        [
            max(abs(red - background[0]), abs(green - background[1]), abs(blue - background[2]))
            for y in range(rgb.height)
            for x in range(rgb.width)
            for red, green, blue in (rgb_pixels[x, y],)
        ]
    )
    mask = difference.point(lambda value: 255 if value > 24 else 0)
    # Encolher ligeiramente antes de procurar componentes separa moedas que
    # apenas se tocam por antialiasing, sombra ou uma faixa muito estreita.
    mask = mask.filter(ImageFilter.MinFilter(5))
    pixels = mask.load()
    visited = bytearray(mask.width * mask.height)
    components: list[tuple[int, float, list[tuple[int, int]]]] = []
    center_x = (mask.width - 1) / 2
    center_y = (mask.height - 1) / 2

    for y in range(mask.height):
        for x in range(mask.width):
            offset = y * mask.width + x
            if visited[offset] or pixels[x, y] == 0:
                continue
            queue = deque([(x, y)])
            visited[offset] = 1
            points: list[tuple[int, int]] = []
            closest = float("inf")
            while queue:
                current_x, current_y = queue.popleft()
                points.append((current_x, current_y))
                closest = min(
                    closest,
                    (current_x - center_x) ** 2 + (current_y - center_y) ** 2,
                )
                for next_y in range(max(0, current_y - 1), min(mask.height, current_y + 2)):
                    for next_x in range(max(0, current_x - 1), min(mask.width, current_x + 2)):
                        next_offset = next_y * mask.width + next_x
                        if not visited[next_offset] and pixels[next_x, next_y] != 0:
                            visited[next_offset] = 1
                            queue.append((next_x, next_y))
            components.append((len(points), closest, points))

    if not components:
        return image, False, False
    largest = max(size for size, _, _ in components)
    candidates = [component for component in components if component[0] >= largest * 0.35]
    _, _, kept_points = min(candidates, key=lambda component: (component[1], -component[0]))
    keep_mask = Image.new("L", rgb.size)
    keep_pixels = keep_mask.load()
    for x, y in kept_points:
        keep_pixels[x, y] = 255
    keep_mask = keep_mask.filter(ImageFilter.MaxFilter(7))
    cleaned = Image.composite(rgb, Image.new("RGB", rgb.size, background), keep_mask)
    removed = sum(size for size, _, points in components if points is not kept_points) > 0
    object_box = keep_mask.getbbox()
    centered = False
    if object_box:
        left, top, right, bottom = object_box
        shift_x = round((rgb.width - (left + right)) / 2)
        shift_y = round((rgb.height - (top + bottom)) / 2)
        if shift_x or shift_y:
            centered_image = Image.new("RGB", rgb.size, background)
            centered_image.paste(cleaned, (shift_x, shift_y))
            cleaned = centered_image
            centered = True
    return cleaned, removed, centered


class CropperServer(ThreadingHTTPServer):
    output_dir: Path
    bootstrap_source: Path | None
    records_cache: list[dict[str, object]] | None
    records_by_id: dict[str, dict[str, object]]
    source_cache: dict[str, str]


class Handler(BaseHTTPRequestHandler):
    server: CropperServer

    def log_message(self, message: str, *args: object) -> None:
        print(f"[cropper] {message % args}")

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def pending_records(self) -> list[dict[str, object]]:
        if self.server.records_cache is None:
            self.server.records_cache = load_pending_souvenirs()
            self.server.records_by_id = {
                str(record["id"]): record for record in self.server.records_cache
            }
        return self.server.records_cache

    def public_record(
        self,
        record: dict[str, object],
        prepared: dict[str, object],
        photo_statuses: dict[str, object],
    ) -> dict[str, object]:
        record_id = str(record["id"])
        manifest_entry = prepared.get(record_id)
        photo_entry = photo_statuses.get(photo_status_key(record))
        output_file = Path(str(manifest_entry.get("file") or "")) if isinstance(manifest_entry, dict) else None
        return {
            "id": record_id,
            "name": str(record.get("name") or "Sem nome"),
            "description": str(record.get("description") or ""),
            "location_id": str(record["_location_id"]),
            "location_name": str(record.get("location_name") or "(sem nome)"),
            "machine": int(record["_machine"]),
            "position": int(record["_position"]),
            "orientation": str(record["_orientation"]),
            "slug": str(record["_slug"]),
            "prepared": isinstance(manifest_entry, dict),
            "photo_completed": bool(
                isinstance(photo_entry, dict) and photo_entry.get("completed")
            ),
            "output_url": f"/output/{output_file.name}" if output_file and output_file.name else "",
            "output_filename": output_file.name if output_file else "",
        }

    def location_rows(self) -> list[dict[str, object]]:
        grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
        for record in self.pending_records():
            key = (
                str(record["_location_id"]),
                str(record.get("location_name") or "(sem nome)"),
            )
            grouped.setdefault(key, []).append(record)
        return [
            {
                "id": location_id,
                "name": name,
                "count": len(records),
                "machines": len({str(record.get("image_front") or "") for record in records}),
            }
            for (location_id, name), records in sorted(
                grouped.items(), key=lambda item: (item[0][1].casefold(), item[0][0])
            )
        ]

    def prepare_record_source(self, record_id: str) -> dict[str, str]:
        record = self.server.records_by_id.get(record_id)
        if record is None:
            raise ValueError("Souvenir não encontrado na fila desta location.")
        source_url = str(record.get("image_front") or "")
        source_id = self.server.source_cache.get(source_url)
        if source_id:
            return {"source_id": source_id, "url": f"/source/{source_id}"}
        data = direct_download(source_url, str(record.get("reference_url") or ""))
        with Image.open(BytesIO(data)) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
        source_id = uuid.uuid4().hex
        destination = self.server.output_dir / "sources" / f"{source_id}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, "PNG")
        self.server.source_cache[source_url] = source_id
        return {"source_id": source_id, "url": f"/source/{source_id}"}

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/":
            data = PAGE.encode()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/api/locations":
            try:
                self.send_json({"locations": self.location_rows()})
            except Exception as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/location-records":
            try:
                location_id = parse_qs(urlparse(self.path).query).get("location", [""])[0]
                prepared = read_manifest(self.server.output_dir)
                photo_statuses = read_photo_status(self.server.output_dir)
                records = [
                    self.public_record(record, prepared, photo_statuses)
                    for record in self.pending_records()
                    if str(record["_location_id"]) == location_id
                ]
                self.send_json({"records": records})
            except Exception as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path.startswith("/api/record-source/"):
            try:
                record_id = Path(path).name
                self.pending_records()
                self.send_json(self.prepare_record_source(record_id))
            except Exception as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path.startswith("/source/"):
            source_id = Path(path).name
            if not re.fullmatch(r"[a-f0-9]{32}", source_id):
                self.send_error(HTTPStatus.BAD_REQUEST)
                return
            self.send_file(self.server.output_dir / "sources" / f"{source_id}.png")
            return
        if path == "/api/bootstrap":
            source = self.server.bootstrap_source
            self.send_json({"url": "/bootstrap-image", "name": source.name} if source else {})
            return
        if path == "/bootstrap-image" and self.server.bootstrap_source:
            self.send_file(self.server.bootstrap_source)
            return
        if path.startswith("/output/"):
            filename = Path(unquote(path.removeprefix("/output/"))).name
            self.send_file(self.server.output_dir / "crops" / filename)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = urlparse(self.path).path
            if path == "/api/source":
                self.save_source()
            elif path == "/api/crop":
                self.save_crop()
            elif path == "/api/photo-status":
                self.save_photo_status()
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (OSError, ValueError, KeyError, Image.UnidentifiedImageError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def request_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 30 * 1024 * 1024:
            raise ValueError("A imagem deve ter entre 1 byte e 30 MB.")
        return self.rfile.read(length)

    def save_photo_status(self) -> None:
        payload = json.loads(self.request_body())
        location_id = str(payload.get("location_id") or "")
        machine = int(payload.get("machine"))
        completed = bool(payload.get("completed"))
        matching = [
            record
            for record in self.pending_records()
            if str(record["_location_id"]) == location_id
            and int(record["_machine"]) == machine
        ]
        if not matching:
            raise ValueError("Fotografia não encontrada nesta location.")
        if completed:
            manifest = read_manifest(self.server.output_dir)
            missing = [record for record in matching if str(record["id"]) not in manifest]
            if missing:
                raise ValueError("Ainda existem moedas desta fotografia por recortar.")
        for record in matching:
            set_photo_status(self.server.output_dir, record, completed)
        self.send_json({"completed": completed, "machine": machine})

    def save_source(self) -> None:
        data = self.request_body()
        with Image.open(BytesIO(data)) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
        source_id = uuid.uuid4().hex
        destination = self.server.output_dir / "sources" / f"{source_id}.png"
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.save(destination, "PNG")
        self.send_json({"source_id": source_id, "path": str(destination), "width": image.width, "height": image.height})

    def save_crop(self) -> None:
        payload = json.loads(self.request_body())
        source_id = str(payload["source_id"])
        if not re.fullmatch(r"[a-f0-9]{32}", source_id):
            raise ValueError("Identificador da imagem inválido.")
        source = self.server.output_dir / "sources" / f"{source_id}.png"
        if not source.is_file():
            raise ValueError("A imagem original já não está disponível.")
        orientation = str(payload.get("orientation") or "landscape")
        sizes = {"landscape": (200, 115), "portrait": (80, 140)}
        if orientation not in sizes:
            raise ValueError("Formato final inválido.")
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            x = round(float(payload["x"]))
            y = round(float(payload["y"]))
            width = round(float(payload["width"]))
            height = round(float(payload["height"]))
            padding = max(0, min(100, round(float(payload.get("padding", 0)))))
            target_ratio = sizes[orientation][0] / sizes[orientation][1]
            expanded_width = max(width + 2 * padding, (height + 2 * padding) * target_ratio)
            expanded_height = expanded_width / target_ratio
            scale = min(1.0, image.width / expanded_width, image.height / expanded_height)
            expanded_width *= scale
            expanded_height *= scale
            center_x = x + width / 2
            center_y = y + height / 2
            left = round(max(0, min(image.width - expanded_width, center_x - expanded_width / 2)))
            top = round(max(0, min(image.height - expanded_height, center_y - expanded_height / 2)))
            right = round(left + expanded_width)
            bottom = round(top + expanded_height)
            if right - left < 5 or bottom - top < 5:
                raise ValueError("O recorte selecionado é demasiado pequeno.")
            cropped = image.crop((left, top, right, bottom))
        cleaned = False
        centered = False
        if bool(payload.get("cleanup", True)):
            cropped, cleaned, centered = clean_isolated_edge_residue(cropped)
        cropped = cropped.resize(sizes[orientation], Image.Resampling.LANCZOS)
        record_id = str(payload.get("record_id") or "")
        record = None
        if record_id:
            self.pending_records()
            record = self.server.records_by_id.get(record_id)
            if record is None:
                raise ValueError("A moeda selecionada já não pertence à fila pendente.")
        base = str(record["_slug"]) if record else slugify(str(payload.get("name") or "recorte"))
        folder = self.server.output_dir / "crops"
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / f"{base}.jpg"
        if record is None:
            suffix = 2
            while destination.exists():
                destination = folder / f"{base}-{suffix}.jpg"
                suffix += 1
        cropped.save(destination, "JPEG", quality=95, subsampling=0)
        if record is not None:
            write_manifest(
                self.server.output_dir,
                record_id,
                {
                    "record_id": record_id,
                    "name": str(record.get("name") or ""),
                    "slug": base,
                    "location_id": str(record["_location_id"]),
                    "location_name": str(record.get("location_name") or ""),
                    "machine": int(record["_machine"]),
                    "position": int(record["_position"]),
                    "source_url": str(record.get("image_front") or ""),
                    "reference_url": str(record.get("reference_url") or ""),
                    "file": str(destination),
                    "orientation": orientation,
                    "crop": {"x": x, "y": y, "width": width, "height": height},
                    "padding": padding,
                    "cleaned": cleaned,
                    "centered": centered,
                },
            )
            set_photo_status(self.server.output_dir, record, False)
        self.send_json({
            "filename": destination.name,
            "path": str(destination),
            "url": f"/output/{destination.name}",
            "width": cropped.width,
            "height": cropped.height,
            "orientation": orientation,
            "cleaned": cleaned,
            "centered": centered,
            "record_id": record_id or None,
        })

    def send_file(self, path: Path) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Abre um recortador local de imagens de Souvenirs.")
    parser.add_argument("--image", type=Path, help="Imagem a abrir inicialmente.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Pasta de teste para originais e recortes.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Não abre o browser automaticamente.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    bootstrap = args.image.resolve() if args.image else None
    if bootstrap and not bootstrap.is_file():
        raise SystemExit(f"Imagem não encontrada: {bootstrap}")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    server = CropperServer((args.host, args.port), Handler)
    server.output_dir = output
    server.bootstrap_source = bootstrap
    server.records_cache = None
    server.records_by_id = {}
    server.source_cache = {}
    url = f"http://{args.host}:{args.port}"
    print(f"Recortador disponível em {url}")
    print(f"Recortes de teste: {output / 'crops'}")
    print("Termina com Ctrl+C.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nRecortador terminado.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
