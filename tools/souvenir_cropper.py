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
from threading import Thread
from urllib.parse import parse_qs, unquote, urlparse

from PIL import Image, ImageFilter, ImageOps


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "recortes_souvenir_teste"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sync_catalog_images_api import direct_download, unique_record_slugs  # noqa: E402
from tools.souvenir_formats import (  # noqa: E402
    SIDE_FIELDS,
    SUPPORTED_SIDES,
    SUPPORTED_SOUVENIR_TYPES,
    crop_size,
    display_orientation_for_crop,
    normalize_crop_format,
)
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
  <p class="hint">Filtra por continente, país, cidade e location. Recorta cada frente ou verso indicado; também podes colar outra montagem com Ctrl+V.</p>
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
      <label for="scope">Estado</label>
      <select id="scope">
        <option value="pending">Por tratar</option>
        <option value="all">Todos com imagem</option>
      </select>
      <label for="continent">Continente</label>
      <select id="continent"><option value="">A carregar…</option></select>
      <label for="country">País</label>
      <select id="country" disabled><option value="">Escolhe um continente…</option></select>
      <label for="city">Cidade</label>
      <select id="city" disabled><option value="">Escolhe um país…</option></select>
      <label for="location">Location</label>
      <select id="location" disabled>
        <option value="">Escolhe uma cidade…</option>
      </select>
      <label for="machine">Fotografia / lado</label>
      <select id="machine" disabled>
        <option value="">Escolhe primeiro uma location</option>
      </select>
      <div id="assignment" class="status assignment">Escolhe uma location para começar.</div>
      <hr>
      <strong>Recorte selecionado</strong>
      <div id="coords" class="status">Ainda não selecionaste um souvenir.</div>
      <label for="orientation">Formato final</label>
      <select id="orientation">
        <option value="landscape">Deitada — 200 × 115 px</option>
        <option value="portrait">Em pé — 80 × 140 px</option>
      </select>
      <label for="padding">Margem adicional (px)</label>
      <input id="padding" type="number" min="0" max="100" value="4">
      <label class="check"><input id="cleanup" type="checkbox" checked><span>Limpar resíduos das bordas e centrar o elemento principal</span></label>
      <button id="save" disabled>Guardar recorte</button>
      <button id="clear" class="secondary" disabled>Limpar seleção</button>
      <hr>
      <strong>Enviar fotografias concluídas</strong>
      <div id="location-finalize" class="status">Marca uma ou mais fotografias como concluídas para as enviar.</div>
      <button id="finalize-location" disabled>Finalizar e enviar concluídas</button>
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
const scopeInput = document.querySelector('#scope');
const continentInput = document.querySelector('#continent');
const countryInput = document.querySelector('#country');
const cityInput = document.querySelector('#city');
const locationInput = document.querySelector('#location');
const assignment = document.querySelector('#assignment');
const photoProgress = document.querySelector('#photo-progress');
const photoState = document.querySelector('#photo-state');
const photoCount = document.querySelector('#photo-count');
const completePhotoButton = document.querySelector('#complete-photo');
const finalizeStatus = document.querySelector('#location-finalize');
const finalizeButton = document.querySelector('#finalize-location');
let pipelineEnabled = false;
let locations = [];
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
  if (orientationInput.value === 'square') return {width:140, height:140};
  if (currentRecord && currentRecord.type === 'pressed') {
    return orientationInput.value === 'portrait' ? {width:80, height:140} : {width:200, height:115};
  }
  return orientationInput.value === 'portrait' ? {width:140, height:200} : {width:200, height:140};
}

function updateFormatOptions() {
  if (!currentRecord) return;
  const square = currentRecord.type === 'coin' || ['circle', 'square'].includes(currentRecord.display_shape);
  if (square) {
    orientationInput.innerHTML = '<option value="square">Quadrado — 140 × 140 px</option>';
  } else if (currentRecord.type === 'pressed') {
    orientationInput.innerHTML = '<option value="landscape">Deitada — 200 × 115 px</option><option value="portrait">Em pé — 80 × 140 px</option>';
  } else {
    orientationInput.innerHTML = '<option value="landscape">Deitada — 200 × 140 px</option><option value="portrait">Em pé — 140 × 200 px</option>';
  }
  orientationInput.value = currentRecord.format;
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
    : 'Ainda não selecionaste um souvenir.';
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
  const label = items[0]?.photo_label || `Fotografia ${machine}`;
  return `${label} · ${prepared}/${items.length} recortes${completed ? ' · completa' : ''}`;
}

function updateLocationProgress() {
  const completedRecords = records.filter(record => record.prepared && record.photo_completed);
  const completedMachines = new Set(completedRecords.map(record => record.machine));
  if (!records.length) {
    finalizeStatus.textContent = 'Escolhe uma location para acompanhar as fotografias.';
    finalizeButton.disabled = true;
    return;
  }
  if (!pipelineEnabled) {
    finalizeStatus.textContent = 'O envio automático só está disponível quando abres o recortador pelo main.py.';
    finalizeButton.disabled = true;
    return;
  }
  finalizeButton.disabled = false;
  if (completedRecords.length) {
    const sideWord = completedRecords.length === 1 ? 'lado' : 'lados';
    const photoWord = completedMachines.size === 1 ? 'fotografia concluída' : 'fotografias concluídas';
    finalizeStatus.textContent = `${completedRecords.length} ${sideWord} em ${completedMachines.size} ${photoWord} serão enviados. Os restantes ficam guardados para depois.`;
    return;
  }
  finalizeStatus.textContent = 'Ainda não marcaste nenhuma fotografia como concluída. Os recortes em curso não serão enviados.';
}


function updatePhotoProgress() {
  updateLocationProgress();
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
  photoCount.textContent = `${prepared}/${items.length} recortes preparados · ${items[0]?.photo_label || `Fotografia ${currentMachine}`}`;
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
      const side = record.side === 'back' ? 'Verso' : 'Frente';
      name.textContent = `${record.name} · ${side}`;
      const state = document.createElement('small');
      state.className = 'coin-state';
      const formatLabel = record.format === 'square' ? 'Quadrado' : (record.format === 'portrait' ? 'Em pé' : 'Deitada');
      const progressLabel = record.prepared ? 'Preparado' : (record.internal ? 'Já interno · pode ser revisto' : 'Por recortar');
      state.textContent = `${record.type} · Posição ${record.position} · ${formatLabel} · ${progressLabel}`;
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
    statusBox.textContent = 'Fotografia carregada. Seleciona o souvenir indicado.';
  };
  image.src = URL.createObjectURL(blob);
}

async function selectRecord(index) {
  if (index < 0 || index >= records.length) return;
  currentIndex = index;
  currentRecord = records[index];
  currentMachine = currentRecord.machine;
  cleanupInput.checked = ['pressed', 'coin'].includes(currentRecord.type);
  updateFormatOptions();
  selection = null;
  draw();
  updateSelection();
  renderMachineGallery();
  const machineItems = recordsForMachine(currentMachine);
  const numberInMachine = machineItems.findIndex(record => record.id === currentRecord.id) + 1;
  assignment.textContent =
    `Recorta este souvenir · ${currentRecord.side === 'back' ? 'Verso' : 'Frente'}:\n${currentRecord.name}\nTipo: ${currentRecord.type} · Formato: ${currentRecord.format}\n${currentRecord.photo_label} · Posição ${currentRecord.position}\n` +
    `Nesta fotografia: ${numberInMachine}/${machineItems.length}`;
  statusBox.textContent = 'A carregar a fotografia deste lado…';
  const response = await fetch(`/api/record-source/${encodeURIComponent(currentRecord.id)}`);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Não foi possível carregar a fotografia da máquina.');
  if (sourceId === result.source_id && image.complete && image.naturalWidth) {
    statusBox.textContent = 'Fotografia carregada. Seleciona o souvenir indicado.';
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
  assignment.textContent = 'A carregar os lados desta location…';
  const response = await fetch(`/api/location-records?location=${encodeURIComponent(locationId)}&scope=${encodeURIComponent(scopeInput.value)}`);
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
    assignment.textContent = 'Esta location não tem lados externos pendentes.';
    saved.innerHTML = '';
    updatePhotoProgress();
    return;
  }
  const firstPending = records.find(record => !record.prepared);
  const firstMachine = firstPending ? firstPending.machine : machines[0];
  machineInput.value = String(firstMachine);
  await selectMachine(firstMachine);
}

function uniqueValues(items, field) {
  return [...new Set(items.map(item => item[field]))].sort((a, b) => a.localeCompare(b, 'pt'));
}

function fillSelect(select, values, placeholder) {
  select.innerHTML = '';
  const empty = document.createElement('option');
  empty.value = '';
  empty.textContent = placeholder;
  select.appendChild(empty);
  values.forEach(value => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
  select.disabled = values.length === 0;
}

function locationsAtCurrentLevel() {
  return locations.filter(location =>
    (!continentInput.value || location.continent === continentInput.value) &&
    (!countryInput.value || location.country === countryInput.value) &&
    (!cityInput.value || location.city === cityInput.value)
  );
}

function updateLocations() {
  const matches = locationsAtCurrentLevel();
  locationInput.innerHTML = '<option value="">Escolhe uma location…</option>';
  matches.forEach(location => {
    const option = document.createElement('option');
    option.value = location.id;
    option.textContent = `${location.name} · ${location.count} souvenirs / ${location.sides} lados / ${location.photos} fotografias`;
    locationInput.appendChild(option);
  });
  locationInput.disabled = matches.length === 0;
  if (matches.length === 1) {
    locationInput.value = matches[0].id;
    loadLocation(matches[0].id).catch(showError);
  } else {
    loadLocation('').catch(showError);
  }
}

function updateCities() {
  const matches = locations.filter(location =>
    location.continent === continentInput.value && location.country === countryInput.value
  );
  const values = uniqueValues(matches, 'city');
  fillSelect(cityInput, values, 'Escolhe uma cidade…');
  locationInput.innerHTML = '<option value="">Escolhe uma cidade…</option>';
  locationInput.disabled = true;
  if (values.length === 1) {
    cityInput.value = values[0];
    updateLocations();
  } else {
    loadLocation('').catch(showError);
  }
}

function updateCountries() {
  const matches = locations.filter(location => location.continent === continentInput.value);
  const values = uniqueValues(matches, 'country');
  fillSelect(countryInput, values, 'Escolhe um país…');
  cityInput.innerHTML = '<option value="">Escolhe um país…</option>';
  cityInput.disabled = true;
  locationInput.innerHTML = '<option value="">Escolhe uma cidade…</option>';
  locationInput.disabled = true;
  if (values.length === 1) {
    countryInput.value = values[0];
    updateCities();
  } else {
    loadLocation('').catch(showError);
  }
}

async function loadLocations() {
  const response = await fetch(`/api/locations?scope=${encodeURIComponent(scopeInput.value)}`);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Não foi possível consultar as locations.');
  locations = result.locations || [];
  fillSelect(countryInput, [], 'Escolhe um continente…');
  fillSelect(cityInput, [], 'Escolhe um país…');
  fillSelect(locationInput, [], 'Escolhe uma cidade…');
  loadLocation('').catch(showError);
  if (!locations.length) {
    continentInput.innerHTML = '<option value="">Não existem lados externos pendentes</option>';
    continentInput.disabled = true;
    countryInput.disabled = true;
    cityInput.disabled = true;
    locationInput.disabled = true;
    assignment.textContent = 'Todos os lados com imagem já usam URLs internos.';
    statusBox.textContent = 'Fila concluída. Novas imagens externas aparecerão aqui automaticamente.';
    finalizeStatus.textContent = 'Não existem fotografias concluídas por enviar.';
    finalizeButton.disabled = true;
    return;
  }
  const continents = uniqueValues(locations, 'continent');
  fillSelect(continentInput, continents, 'Escolhe um continente…');
  if (continents.length === 1) {
    continentInput.value = continents[0];
    updateCountries();
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
    assignment.textContent = `${items[0]?.photo_label || `Fotografia ${currentMachine}`} concluída: ${items.length}/${items.length} recortes preparados.`;
    currentRecord = null;
    selection = null;
    renderMachineGallery();
    draw();
    updateSelection();
  }
}

scopeInput.onchange = () => loadLocations().catch(showError);
continentInput.onchange = () => updateCountries();
countryInput.onchange = () => updateCities();
cityInput.onchange = () => updateLocations();
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
      location_id: locationInput.value, machine: currentMachine, completed, scope: scopeInput.value
    })});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Não foi possível alterar o estado da fotografia.');
    items.forEach(record => { record.photo_completed = completed; });
    updateMachineOption(currentMachine);
    updatePhotoProgress();
    assignment.textContent = completed
      ? `${items[0]?.photo_label || `Fotografia ${currentMachine}`} confirmada como completa.`
      : `${items[0]?.photo_label || `Fotografia ${currentMachine}`} reaberta para revisão.`;
  } catch (error) { showError(error); updatePhotoProgress(); }
};

finalizeButton.onclick = async () => {
  if (!pipelineEnabled) return;
  const completedRecords = records.filter(record => record.prepared && record.photo_completed);
  const completedMachines = new Set(completedRecords.map(record => record.machine));
  if (!completedRecords.length) {
    finalizeStatus.textContent = 'Marca pelo menos uma fotografia como concluída antes de enviar.';
    return;
  }
  const locationName = locationInput.selectedOptions[0]?.textContent || locationInput.value;
  const sideWord = completedRecords.length === 1 ? 'lado' : 'lados';
  const photoWord = completedMachines.size === 1 ? 'fotografia concluída' : 'fotografias concluídas';
  const confirmed = window.confirm(
    `Enviar ${completedRecords.length} ${sideWord} de ${completedMachines.size} ${photoWord} em ${locationName}?\n\nAs fotografias ainda abertas ficam guardadas e não serão enviadas.`
  );
  if (!confirmed) return;
  finalizeButton.disabled = true;
  finalizeStatus.textContent = 'Pedido enviado. Acompanha no terminal: validar → publicar → verificar → atualizar Base44.';
  statusBox.textContent = 'A enviar apenas as fotografias concluídas. O processamento continua automaticamente no terminal.';
  try {
    const response = await fetch('/api/finalize', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({location_id: locationInput.value, scope: scopeInput.value})
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Não foi possível enviar as fotografias concluídas.');
    finalizeStatus.textContent = result.message || 'Envio iniciado. Acompanha o resultado no terminal.';
  } catch (error) {
    showError(error);
    updateLocationProgress();
  }
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
    const centeredText = result.centered ? ' · elemento centrado' : '';
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
  pipelineEnabled = Boolean(result.can_finalize);
  updateLocationProgress();
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
    explicit = str(query.get("location", [""])[0]).strip()
    if explicit:
        return explicit
    identity = "|".join(
        str(record.get(field) or "").strip().casefold()
        for field in ("continent", "country", "city", "location_name")
    )
    digest = hashlib.sha256(identity.encode()).hexdigest()[:12]
    return f"geo-{digest}"


def record_machine_position(record: dict[str, object]) -> tuple[int, int]:
    reference = str(record.get("reference_url") or "")
    match = re.search(
        r"#(?:retired-)?machine-(\d+)-position-(\d+)",
        reference,
        re.IGNORECASE,
    )
    if not match:
        match = re.search(
            r"Machine\s+(\d+)\s*[·|-]\s*Posição\s+(\d+)",
            str(record.get("notes") or ""),
            re.IGNORECASE,
        )
    if match:
        return int(match.group(1)), int(match.group(2))
    return (
        int(record.get("machine") or 9999),
        int(record.get("ordem") or record.get("position") or 9999),
    )


def record_crop_format(record: dict[str, object]) -> str:
    requested = str(record.get("display_orientation") or "")
    if requested not in {"portrait", "landscape"}:
        notes = str(record.get("notes") or "").casefold()
        requested = "portrait" if "vertical" in notes else "landscape"
    return normalize_crop_format(
        record.get("type"),
        requested,
        record.get("display_shape"),
    )


def build_souvenir_tasks(
    records: list[dict[str, object]], *, include_internal: bool = False
) -> list[dict[str, object]]:
    supported = [
        record
        for record in records
        if str(record.get("type") or "") in SUPPORTED_SOUVENIR_TYPES
    ]
    slugs = unique_record_slugs(supported, "souvenir")
    tasks: list[dict[str, object]] = []
    for record in supported:
        record_id = str(record.get("id") or "")
        if not record_id:
            continue
        location_id = record_location_id(record)
        original_machine, original_position = record_machine_position(record)
        side_sources = {
            side: str(record.get(SIDE_FIELDS[side]) or "").strip()
            for side in SUPPORTED_SIDES
        }
        for side in SUPPORTED_SIDES:
            source = side_sources[side]
            source_side = side
            source_was_empty = not source
            if source_was_empty and str(record.get("type") or "") == "coin":
                source_side = "back" if side == "front" else "front"
                source = side_sources[source_side]
            internal = bool(side_sources[side]) and side_sources[side].startswith(
                DEFAULT_RAW_BASE_URL
            )
            if not source or (internal and not include_internal):
                continue
            task = dict(record)
            task["id"] = f"{record_id}:{side}"
            task["_record_id"] = record_id
            task["_side"] = side
            task["_source_url"] = source
            task["_source_side"] = source_side
            task["_source_was_empty"] = source_was_empty
            task["_internal"] = internal
            task["_location_id"] = location_id
            task["_original_machine"] = original_machine
            task["_original_position"] = original_position
            task["_format"] = record_crop_format(record)
            task["_slug"] = slugs[record_id]
            tasks.append(task)

    by_location: dict[str, list[dict[str, object]]] = {}
    for task in tasks:
        by_location.setdefault(str(task["_location_id"]), []).append(task)
    for location_tasks in by_location.values():
        photo_keys = sorted(
            {
                (
                    int(task["_original_machine"]),
                    0 if task["_side"] == "front" else 1,
                    str(task["_source_url"]),
                )
                for task in location_tasks
            }
        )
        photo_numbers = {key: index for index, key in enumerate(photo_keys, 1)}
        grouped: dict[tuple[int, int, str], list[dict[str, object]]] = {}
        for task in location_tasks:
            key = (
                int(task["_original_machine"]),
                0 if task["_side"] == "front" else 1,
                str(task["_source_url"]),
            )
            task["_machine"] = photo_numbers[key]
            grouped.setdefault(key, []).append(task)
        for photo_tasks in grouped.values():
            photo_tasks.sort(
                key=lambda task: (
                    int(task["_original_position"]),
                    int(task.get("ordem") or 9999),
                    str(task.get("name") or "").casefold(),
                    str(task["_record_id"]),
                )
            )
            positions = [int(task["_original_position"]) for task in photo_tasks]
            use_original = all(value != 9999 for value in positions) and len(set(positions)) == len(positions)
            for index, task in enumerate(photo_tasks, 1):
                task["_position"] = int(task["_original_position"]) if use_original else index
                side_label = "Frente" if task["_side"] == "front" else "Verso"
                task["_photo_label"] = f"Fotografia {task['_machine']} · {side_label}"

    return sorted(
        tasks,
        key=lambda item: (
            str(item.get("continent") or "").casefold(),
            str(item.get("country") or "").casefold(),
            str(item.get("city") or "").casefold(),
            str(item.get("location_name") or "").casefold(),
            str(item["_location_id"]),
            int(item["_machine"]),
            int(item["_position"]),
            str(item.get("name") or "").casefold(),
        ),
    )


def load_pending_souvenirs(*, include_internal: bool = False) -> list[dict[str, object]]:
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        raise RuntimeError(f"Define {API_KEY_ENV} no ficheiro .env.")
    data = api_request(
        "GET",
        "/entities/Souvenir",
        api_key,
        query={"limit": 5000},
    )
    if not isinstance(data, list):
        raise RuntimeError(f"Resposta inesperada ao listar Souvenirs: {data!r}")
    return build_souvenir_tasks(
        [row for row in data if isinstance(row, dict)],
        include_internal=include_internal,
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


def manifest_entry_for_task(
    manifest: dict[str, object], task: dict[str, object]
) -> dict[str, object] | None:
    task_id = str(task["id"])
    entry = manifest.get(task_id)
    if not isinstance(entry, dict) and task.get("_side") == "front":
        entry = manifest.get(str(task.get("_record_id") or ""))
    return entry if isinstance(entry, dict) else None


def write_manifest(output_dir: Path, task_id: str, entry: dict[str, object]) -> None:
    manifest = read_manifest(output_dir)
    legacy_id = str(entry.get("record_id") or "")
    if entry.get("side") == "front" and legacy_id != task_id:
        manifest.pop(legacy_id, None)
    manifest[task_id] = entry
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
    source_url = str(record.get("_source_url") or record.get("source_url") or record.get("image_front") or "")
    source_hash = hashlib.sha256(source_url.encode()).hexdigest()[:12]
    return f"{record['_location_id']}:photo-{record['_machine']}:{source_hash}"


def photo_status_for_task(
    statuses: dict[str, object], task: dict[str, object]
) -> dict[str, object] | None:
    current = statuses.get(photo_status_key(task))
    if isinstance(current, dict):
        return current
    source = str(task.get("_source_url") or "")
    side = str(task.get("_side") or "front")
    for value in statuses.values():
        if (
            isinstance(value, dict)
            and str(value.get("source_url") or "") == source
            and str(value.get("side") or "front") == side
        ):
            return value
    return None


def set_photo_status(output_dir: Path, record: dict[str, object], completed: bool) -> None:
    statuses = read_photo_status(output_dir)
    key = photo_status_key(record)
    statuses[key] = {
        "completed": completed,
        "location_id": str(record["_location_id"]),
        "location_name": str(record.get("location_name") or ""),
        "machine": int(record["_machine"]),
        "source_url": str(record.get("_source_url") or ""),
        "side": str(record.get("_side") or "front"),
    }
    (output_dir / "photo-status.json").write_text(
        json.dumps(statuses, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def clean_isolated_edge_residue(image: Image.Image) -> tuple[Image.Image, bool, bool]:
    """Remove apenas objetos estranhos ligados às bordas do recorte.

    O desenho de uma moeda pode conter letras e ilustrações desconectadas.
    Esses componentes interiores têm de ser preservados; apenas componentes
    que entram no recorte através de uma borda são considerados resíduos.
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
    pixels = mask.load()
    visited = bytearray(mask.width * mask.height)
    components: list[tuple[int, float, bool, list[tuple[int, int]]]] = []
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
            touches_border = False
            while queue:
                current_x, current_y = queue.popleft()
                points.append((current_x, current_y))
                touches_border = touches_border or (
                    current_x == 0
                    or current_y == 0
                    or current_x == mask.width - 1
                    or current_y == mask.height - 1
                )
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
            components.append((len(points), closest, touches_border, points))

    if not components:
        return image, False, False
    largest = max(size for size, _, _, _ in components)
    candidates = [component for component in components if component[0] >= largest * 0.35]
    main_component = min(candidates, key=lambda component: (component[1], -component[0]))

    remove_mask = Image.new("L", rgb.size)
    remove_pixels = remove_mask.load()
    removed = False
    for component in components:
        _, _, touches_border, points = component
        if component is main_component or not touches_border:
            continue
        removed = True
        for x, y in points:
            remove_pixels[x, y] = 255

    if removed:
        # Inclui o antialiasing que rodeia o resíduo, sem tocar em elementos
        # interiores da moeda.
        remove_mask = remove_mask.filter(ImageFilter.MaxFilter(5))
        cleaned = Image.composite(Image.new("RGB", rgb.size, background), rgb, remove_mask)
    else:
        cleaned = rgb

    main_mask = Image.new("L", rgb.size)
    main_pixels = main_mask.load()
    for x, y in main_component[3]:
        main_pixels[x, y] = 255
    main_mask = main_mask.filter(ImageFilter.MaxFilter(7))
    object_box = main_mask.getbbox()
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


def completion_request(
    output_dir: Path,
    records: list[dict[str, object]],
    location_id: str,
) -> dict[str, object]:
    matching = [record for record in records if str(record["_location_id"]) == location_id]
    if not matching:
        raise ValueError("Esta location já não pertence à fila de trabalho.")
    manifest = read_manifest(output_dir)
    statuses = read_photo_status(output_dir)
    completed_tasks: list[dict[str, object]] = []
    completed_photos: list[int] = []
    for machine in sorted({int(record["_machine"]) for record in matching}):
        photo_tasks = [record for record in matching if int(record["_machine"]) == machine]
        status = photo_status_for_task(statuses, photo_tasks[0])
        if not isinstance(status, dict) or not status.get("completed"):
            continue
        missing = [record for record in photo_tasks if manifest_entry_for_task(manifest, record) is None]
        if missing:
            raise ValueError(
                f"A fotografia {machine} está concluída, mas ainda tem {len(missing)} recortes em falta."
            )
        completed_photos.append(machine)
        completed_tasks.extend(photo_tasks)
    if not completed_tasks:
        raise ValueError("Marca pelo menos uma fotografia como concluída antes de enviar.")
    record_sides = [
        str(record["id"]) if ":" in str(record["id"]) else f"{record['id']}:front"
        for record in completed_tasks
    ]
    record_ids = list(dict.fromkeys(
        str(record.get("_record_id") or str(record["id"]).partition(":")[0])
        for record in completed_tasks
    ))
    first = matching[0]
    return {
        "location_id": location_id,
        "location_name": str(first.get("location_name") or "(sem location)"),
        "continent": str(first.get("continent") or ""),
        "country": str(first.get("country") or ""),
        "city": str(first.get("city") or ""),
        "records": len(record_ids),
        "sides": len(record_sides),
        "photos": len(completed_photos),
        "record_ids": record_ids,
        "record_sides": record_sides,
    }


class CropperServer(ThreadingHTTPServer):
    output_dir: Path
    bootstrap_source: Path | None
    completion_file: Path | None
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

    def pending_records(self, scope: str = "pending") -> list[dict[str, object]]:
        if self.server.records_cache is None:
            self.server.records_cache = load_pending_souvenirs(include_internal=True)
            self.server.records_by_id = {
                str(record["id"]): record for record in self.server.records_cache
            }
        if scope == "all":
            return self.server.records_cache
        return [record for record in self.server.records_cache if not record.get("_internal")]

    def public_record(
        self,
        record: dict[str, object],
        prepared: dict[str, object],
        photo_statuses: dict[str, object],
    ) -> dict[str, object]:
        task_id = str(record["id"])
        manifest_entry = manifest_entry_for_task(prepared, record)
        photo_entry = photo_status_for_task(photo_statuses, record)
        output_file = (
            Path(str(manifest_entry.get("file") or ""))
            if isinstance(manifest_entry, dict)
            else None
        )
        return {
            "id": task_id,
            "record_id": str(record["_record_id"]),
            "side": str(record["_side"]),
            "name": str(record.get("name") or "Sem nome"),
            "description": str(record.get("description") or ""),
            "type": str(record.get("type") or ""),
            "display_shape": str(record.get("display_shape") or ""),
            "continent": str(record.get("continent") or ""),
            "country": str(record.get("country") or ""),
            "city": str(record.get("city") or ""),
            "location_id": str(record["_location_id"]),
            "location_name": str(record.get("location_name") or "(sem location)"),
            "machine": int(record["_machine"]),
            "photo_label": str(record["_photo_label"]),
            "position": int(record["_position"]),
            "format": str(record["_format"]),
            "orientation": display_orientation_for_crop(
                record.get("type"), record["_format"], record.get("display_shape")
            ),
            "slug": str(record["_slug"]),
            "internal": bool(record.get("_internal")),
            "prepared": isinstance(manifest_entry, dict),
            "photo_completed": bool(
                isinstance(photo_entry, dict) and photo_entry.get("completed")
            ),
            "output_url": f"/output/{output_file.name}" if output_file and output_file.name else "",
            "output_filename": output_file.name if output_file else "",
        }

    def location_rows(self, scope: str = "pending") -> list[dict[str, object]]:
        grouped: dict[str, list[dict[str, object]]] = {}
        for record in self.pending_records(scope):
            grouped.setdefault(str(record["_location_id"]), []).append(record)
        rows: list[dict[str, object]] = []
        for location_id, records in grouped.items():
            first = records[0]
            rows.append({
                "id": location_id,
                "name": str(first.get("location_name") or "(sem location)"),
                "continent": str(first.get("continent") or "(sem continente)"),
                "country": str(first.get("country") or "(sem país)"),
                "city": str(first.get("city") or "(sem cidade)"),
                "count": len({str(record["_record_id"]) for record in records}),
                "sides": len(records),
                "photos": len({int(record["_machine"]) for record in records}),
            })
        return sorted(
            rows,
            key=lambda row: (
                str(row["continent"]).casefold(),
                str(row["country"]).casefold(),
                str(row["city"]).casefold(),
                str(row["name"]).casefold(),
                str(row["id"]),
            ),
        )

    def prepare_record_source(self, record_id: str) -> dict[str, str]:
        record = self.server.records_by_id.get(record_id)
        if record is None:
            raise ValueError("Souvenir não encontrado na fila desta location.")
        source_url = str(record.get("_source_url") or "")
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
                scope = parse_qs(urlparse(self.path).query).get("scope", ["pending"])[0]
                self.send_json({"locations": self.location_rows(scope)})
            except Exception as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path == "/api/location-records":
            try:
                query = parse_qs(urlparse(self.path).query)
                location_id = query.get("location", [""])[0]
                scope = query.get("scope", ["pending"])[0]
                prepared = read_manifest(self.server.output_dir)
                photo_statuses = read_photo_status(self.server.output_dir)
                records = [
                    self.public_record(record, prepared, photo_statuses)
                    for record in self.pending_records(scope)
                    if str(record["_location_id"]) == location_id
                ]
                self.send_json({"records": records})
            except Exception as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        if path.startswith("/api/record-source/"):
            try:
                record_id = unquote(Path(path).name)
                self.pending_records("all")
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
            payload: dict[str, object] = {
                "can_finalize": self.server.completion_file is not None,
            }
            if source:
                payload.update({"url": "/bootstrap-image", "name": source.name})
            self.send_json(payload)
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
            elif path == "/api/finalize":
                self.save_finalize()
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
        scope = str(payload.get("scope") or "pending")
        matching = [
            record
            for record in self.pending_records(scope)
            if str(record["_location_id"]) == location_id
            and int(record["_machine"]) == machine
        ]
        if not matching:
            raise ValueError("Fotografia não encontrada nesta location.")
        if completed:
            manifest = read_manifest(self.server.output_dir)
            missing = [
                record for record in matching
                if manifest_entry_for_task(manifest, record) is None
            ]
            if missing:
                raise ValueError("Ainda existem lados desta fotografia por recortar.")
        for record in matching:
            set_photo_status(self.server.output_dir, record, completed)
        self.send_json({"completed": completed, "machine": machine})

    def save_finalize(self) -> None:
        if self.server.completion_file is None:
            raise ValueError("Abre o recortador através do main.py para usar o envio automático.")
        payload = json.loads(self.request_body())
        location_id = str(payload.get("location_id") or "")
        scope = str(payload.get("scope") or "pending")
        request = completion_request(self.server.output_dir, self.pending_records(scope), location_id)
        destination = self.server.completion_file
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(request, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(destination)
        side_word = "lado concluído validado" if request["sides"] == 1 else "lados concluídos validados"
        self.send_json({
            **request,
            "message": (
                f"{request['sides']} {side_word} em {request['records']} Souvenirs. "
                "O envio automático continua no terminal."
            ),
        })
        Thread(target=self.server.shutdown, daemon=True).start()

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
        task_id = str(payload.get("record_id") or "")
        record = None
        if task_id:
            self.pending_records("all")
            record = self.server.records_by_id.get(task_id)
            if record is None:
                raise ValueError("O lado selecionado já não pertence à fila de trabalho.")
        record_type = str(record.get("type") or "pressed") if record else "pressed"
        display_shape = str(record.get("display_shape") or "") if record else ""
        crop_format = normalize_crop_format(
            record_type, payload.get("orientation"), display_shape
        )
        size = crop_size(record_type, crop_format, display_shape)
        with Image.open(source) as opened:
            image = ImageOps.exif_transpose(opened).convert("RGB")
            x = round(float(payload["x"]))
            y = round(float(payload["y"]))
            width = round(float(payload["width"]))
            height = round(float(payload["height"]))
            padding = max(0, min(100, round(float(payload.get("padding", 0)))))
            target_ratio = size[0] / size[1]
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
        cropped = cropped.resize(size, Image.Resampling.LANCZOS)
        base = str(record["_slug"]) if record else slugify(str(payload.get("name") or "recorte"))
        side = str(record.get("_side") or "front") if record else "front"
        folder = self.server.output_dir / "crops"
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / f"{base}-{side}.jpg"
        if record is None:
            suffix = 2
            while destination.exists():
                destination = folder / f"{base}-{side}-{suffix}.jpg"
                suffix += 1
        cropped.save(destination, "JPEG", quality=95, subsampling=0)
        display_orientation = display_orientation_for_crop(
            record_type, crop_format, display_shape
        )
        if record is not None:
            write_manifest(
                self.server.output_dir,
                task_id,
                {
                    "task_id": task_id,
                    "record_id": str(record["_record_id"]),
                    "side": side,
                    "name": str(record.get("name") or ""),
                    "type": record_type,
                    "display_shape": display_shape,
                    "slug": base,
                    "continent": str(record.get("continent") or ""),
                    "country": str(record.get("country") or ""),
                    "city": str(record.get("city") or ""),
                    "location_id": str(record["_location_id"]),
                    "location_name": str(record.get("location_name") or ""),
                    "machine": int(record["_machine"]),
                    "position": int(record["_position"]),
                    "source_url": str(record.get("_source_url") or ""),
                    "source_side": str(record.get("_source_side") or side),
                    "source_was_empty": bool(record.get("_source_was_empty")),
                    "reference_url": str(record.get("reference_url") or ""),
                    "file": str(destination),
                    "format": crop_format,
                    "orientation": display_orientation,
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
            "format": crop_format,
            "orientation": display_orientation,
            "side": side,
            "cleaned": cleaned,
            "centered": centered,
            "record_id": task_id or None,
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
    parser.add_argument("--completion-file", type=Path, help="Ficheiro de sinalização usado pelo fluxo completo do main.py.")
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
    server.completion_file = args.completion_file.resolve() if args.completion_file else None
    server.records_cache = None
    server.records_by_id = {}
    server.source_cache = {}
    url = f"http://{args.host}:{args.port}"
    print(f"Recortador disponível em {url}")
    print(f"Recortes de teste: {output / 'crops'}")
    if server.completion_file:
        print("Usa ‘Finalizar e enviar’ no browser quando a location estiver completa.")
    else:
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
