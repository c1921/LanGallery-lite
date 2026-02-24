<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { fetchImages } from "./api";
import type { ImageItem } from "./types";

const images = ref<ImageItem[]>([]);
const loading = ref(true);
const loadError = ref("");
const viewerOpen = ref(false);
const activeIndex = ref(0);

const activeImage = computed(() => images.value[activeIndex.value] ?? null);
const totalText = computed(() => `${images.value.length} 张`);

function openViewer(index: number): void {
  activeIndex.value = index;
  viewerOpen.value = true;
}

function closeViewer(): void {
  viewerOpen.value = false;
}

function showPrev(): void {
  if (!images.value.length) {
    return;
  }
  activeIndex.value = (activeIndex.value - 1 + images.value.length) % images.value.length;
}

function showNext(): void {
  if (!images.value.length) {
    return;
  }
  activeIndex.value = (activeIndex.value + 1) % images.value.length;
}

async function load(): Promise<void> {
  loading.value = true;
  loadError.value = "";

  try {
    const result = await fetchImages();
    images.value = result.items;
    if (!images.value.length) {
      viewerOpen.value = false;
      activeIndex.value = 0;
    } else if (activeIndex.value >= images.value.length) {
      activeIndex.value = 0;
    }
  } catch (error: unknown) {
    images.value = [];
    loadError.value = error instanceof Error ? error.message : "加载失败";
  } finally {
    loading.value = false;
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (!viewerOpen.value) {
    return;
  }

  if (event.key === "Escape") {
    closeViewer();
  } else if (event.key === "ArrowLeft") {
    showPrev();
  } else if (event.key === "ArrowRight") {
    showNext();
  }
}

onMounted(() => {
  window.addEventListener("keydown", onKeydown);
  void load();
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <main class="page">
    <header class="topbar">
      <div>
        <h1 class="title">LanGallery Lite</h1>
        <p class="subtitle">局域网图片浏览</p>
      </div>
      <div class="actions">
        <span class="count">{{ totalText }}</span>
        <button type="button" class="refresh" :disabled="loading" @click="load">
          刷新
        </button>
      </div>
    </header>

    <p v-if="loading" class="hint">加载中...</p>
    <p v-else-if="loadError" class="hint error">{{ loadError }}</p>
    <p v-else-if="!images.length" class="hint">目录下没有可显示的图片</p>

    <section v-else class="grid">
      <button
        v-for="(item, index) in images"
        :key="item.id"
        type="button"
        class="card"
        @click="openViewer(index)"
      >
        <img :src="item.url" :alt="item.name" loading="lazy" />
      </button>
    </section>
  </main>

  <div v-if="viewerOpen && activeImage" class="viewer" @click.self="closeViewer">
    <header class="viewer-top">
      <p class="viewer-meta">{{ activeIndex + 1 }} / {{ images.length }} · {{ activeImage.name }}</p>
      <button type="button" class="viewer-btn" @click="closeViewer">关闭</button>
    </header>

    <div class="viewer-body">
      <img class="viewer-image" :src="activeImage.url" :alt="activeImage.name" />
    </div>

    <footer class="viewer-actions">
      <button type="button" class="viewer-btn" @click="showPrev">上一张</button>
      <button type="button" class="viewer-btn" @click="showNext">下一张</button>
    </footer>
  </div>
</template>
