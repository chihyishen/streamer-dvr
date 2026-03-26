<template>
  <div class="app-shell">
    <AppToastStack :toasts="store.toasts" />
    <header class="topbar">
      <div class="brand">
        <div class="title display-face">Cam Recorder</div>
      </div>
      <div class="topbar-side">
        <nav class="nav">
          <RouterLink to="/" class="nav-link" active-class="active" exact-active-class="active">Dashboard</RouterLink>
          <RouterLink to="/logs" class="nav-link" active-class="active">Logs</RouterLink>
        </nav>
      </div>
    </header>
    <main class="page-stage">
      <RouterView />
    </main>
  </div>
</template>

<script setup lang="ts">
import { RouterLink, RouterView } from "vue-router";

import AppToastStack from "./components/common/AppToastStack.vue";
import { useAppStore } from "./stores/app";

const store = useAppStore();
</script>

<style>
.app-shell {
  max-width: 1100px;
  margin: 0 auto;
  padding: 64px 24px 80px;
  animation: fade-in 400ms cubic-bezier(0.16, 1, 0.3, 1);
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 24px;
  margin-bottom: 64px;
}

.brand {
  display: grid;
  gap: 4px;
}

.title {
  font-size: 28px;
  line-height: 1;
  letter-spacing: -0.05em;
  font-weight: 800;
  color: var(--text);
}

.topbar-side {
  display: flex;
  align-items: center;
}

.nav {
  display: inline-flex;
  gap: 32px;
  align-items: center;
}

.nav-link {
  text-decoration: none;
  color: var(--muted);
  font-weight: 600;
  font-size: 15px;
  letter-spacing: -0.01em;
  transition: color 200ms ease;
  position: relative;
  padding: 4px 0;
}

.nav-link.active {
  color: var(--text);
}

.nav-link::after {
  content: "";
  position: absolute;
  bottom: 0;
  left: 0;
  width: 100%;
  height: 2px;
  background: var(--text);
  transform: scaleX(0);
  transition: transform 250ms cubic-bezier(0.16, 1, 0.3, 1);
}

.nav-link.active::after {
  transform: scaleX(1);
}

.nav-link:hover:not(.active) {
  color: var(--text);
}

.page-stage {
  position: relative;
}

@media (max-width: 900px) {
  .app-shell {
    padding: 32px 20px 64px;
  }

  .topbar {
    flex-direction: row;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 40px;
    gap: 16px;
  }

  .title {
    font-size: 20px;
  }

  .nav {
    gap: 16px;
  }

  .nav-link {
    font-size: 14px;
  }
}

@media (max-width: 500px) {
  .topbar {
    flex-direction: column;
    align-items: flex-start;
    gap: 20px;
  }
}
</style>
