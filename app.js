const demoChannels = [
  {
    name: "GreenStreem Demo Clip",
    category: "Demo | Video",
    logo: "https://upload.wikimedia.org/wikipedia/commons/d/df/A%26E_Network_logo.svg",
    url: "https://interactive-examples.mdn.mozilla.net/media/cc0-videos/flower.mp4",
    now: "Browser playback test",
  },
  {
    name: "US ABC New York",
    category: "US | News",
    logo: "https://upload.wikimedia.org/wikipedia/commons/2/2f/ABC-2021-LOGO.svg",
    url: "",
    now: "Guide pending",
  },
  {
    name: "US AMC East",
    category: "US | Movies",
    logo: "https://upload.wikimedia.org/wikipedia/commons/3/34/AMC_logo_2019.svg",
    url: "",
    now: "Movie block",
  },
  {
    name: "US Bravo East",
    category: "US | Entertainment",
    logo: "",
    url: "",
    now: "No Information",
  },
  {
    name: "US ESPN",
    category: "US | Sports",
    logo: "https://upload.wikimedia.org/wikipedia/commons/2/2f/ESPN_wordmark.svg",
    url: "",
    now: "SportsCenter",
  },
  {
    name: "UK | Sky Store",
    category: "UK | Movies",
    logo: "",
    url: "",
    now: "Featured",
  },
];

const state = {
  mode: "xtream",
  section: "login",
  sessionId: "",
  defaultServerConfigured: false,
  channels: [...demoChannels],
  activeCategory: "All Channels",
  activeChannelIndex: -1,
  favoritesOnly: false,
  favorites: new Set(JSON.parse(localStorage.getItem("greenstreem:favorites") || "[]")),
  hls: null,
  mpegts: null,
  playbackVideo: null,
  fullscreenControlsTimer: null,
  activeChannel: null,
  triedFallback: false,
  preferredLiveStreamType: localStorage.getItem("greenstreem:preferredLiveStreamType") || "auto",
  pendingTsPreference: false,
  account: {},
  guide: {},
  guidePollTimer: null,
  selectedLibraryItem: null,
  activeLibraryType: "",
  libraries: {
    movies: { loaded: false, loading: false, categories: [], items: [], selectedCategory: "All" },
    series: { loaded: false, loading: false, categories: [], items: [], selectedCategory: "All" },
  },
};

const els = {
  loginView: document.querySelector("#loginView"),
  homeView: document.querySelector("#homeView"),
  playerView: document.querySelector("#playerView"),
  placeholderView: document.querySelector("#placeholderView"),
  libraryView: document.querySelector("#libraryView"),
  accountView: document.querySelector("#accountView"),
  loginForm: document.querySelector("#loginForm"),
  modeTabsContainer: document.querySelector("#modeTabs"),
  modeTabs: document.querySelectorAll(".mode-tab"),
  xtreamFields: document.querySelector("#xtreamFields"),
  serverUrlField: document.querySelector("#serverUrlField"),
  serverUrlInput: document.querySelector("#serverUrlInput"),
  m3uFields: document.querySelector("#m3uFields"),
  channelList: document.querySelector("#channelList"),
  categoryList: document.querySelector("#categoryList"),
  channelSearchInput: document.querySelector("#channelSearchInput"),
  categorySearchInput: document.querySelector("#categorySearchInput"),
  currentCategoryLabel: document.querySelector("#currentCategoryLabel"),
  currentChannelTitle: document.querySelector("#currentChannelTitle"),
  nowTitle: document.querySelector("#nowTitle"),
  nextTitle: document.querySelector("#nextTitle"),
  nowTime: document.querySelector("#nowTime"),
  streamReportButton: document.querySelector("#streamReportButton"),
  streamReport: document.querySelector("#streamReport"),
  videoPlayer: document.querySelector("#videoPlayer"),
  fullscreenPlayer: document.querySelector("#fullscreenPlayer"),
  fullscreenVideoPlayer: document.querySelector("#fullscreenVideoPlayer"),
  fullscreenTitle: document.querySelector("#fullscreenTitle"),
  fullscreenMeta: document.querySelector("#fullscreenMeta"),
  fullscreenStatus: document.querySelector("#fullscreenStatus"),
  closeFullscreenPlayerButton: document.querySelector("#closeFullscreenPlayerButton"),
  categoryDrawer: document.querySelector("#categoryDrawer"),
  drawerScrim: document.querySelector("#drawerScrim"),
  openCategoriesButton: document.querySelector("#openCategoriesButton"),
  closeCategoriesButton: document.querySelector("#closeCategoriesButton"),
  fullscreenButton: document.querySelector("#fullscreenButton"),
  searchButton: document.querySelector("#searchButton"),
  favoritesOnlyButton: document.querySelector("#favoritesOnlyButton"),
  closeCategoryManagerButton: document.querySelector("#closeCategoryManagerButton"),
  resetPlaybackButton: document.querySelector("#resetPlaybackButton"),
  loginStatus: document.querySelector("#loginStatus"),
  accountLoginType: document.querySelector("#accountLoginType"),
  accountChannelCount: document.querySelector("#accountChannelCount"),
  accountFavoriteCount: document.querySelector("#accountFavoriteCount"),
  accountStatus: document.querySelector("#accountStatus"),
  accountExpires: document.querySelector("#accountExpires"),
  accountConnections: document.querySelector("#accountConnections"),
  accountPlaybackMode: document.querySelector("#accountPlaybackMode"),
  accountGuideCount: document.querySelector("#accountGuideCount"),
  accountGuideStatus: document.querySelector("#accountGuideStatus"),
  preferAutoButton: document.querySelector("#preferAutoButton"),
  preferTsButton: document.querySelector("#preferTsButton"),
  clearFavoritesButton: document.querySelector("#clearFavoritesButton"),
  logoutButton: document.querySelector("#logoutButton"),
  libraryEyebrow: document.querySelector("#libraryEyebrow"),
  libraryTitle: document.querySelector("#libraryTitle"),
  librarySearchInput: document.querySelector("#librarySearchInput"),
  libraryCategorySelect: document.querySelector("#libraryCategorySelect"),
  libraryStatus: document.querySelector("#libraryStatus"),
  libraryGrid: document.querySelector("#libraryGrid"),
  itemModal: document.querySelector("#itemModal"),
  closeItemModalButton: document.querySelector("#closeItemModalButton"),
  modalBackButton: document.querySelector("#modalBackButton"),
  modalPoster: document.querySelector("#modalPoster"),
  modalCategory: document.querySelector("#modalCategory"),
  modalTitle: document.querySelector("#modalTitle"),
  modalMeta: document.querySelector("#modalMeta"),
  modalPlot: document.querySelector("#modalPlot"),
  playItemButton: document.querySelector("#playItemButton"),
  placeholderTitle: document.querySelector("#placeholderTitle"),
  placeholderCopy: document.querySelector("#placeholderCopy"),
};

const apiAvailable = window.location.protocol !== "file:";

function setStatus(message) {
  els.loginStatus.textContent = message;
}

function stopLivePreviewForSection(section) {
  if (state.section === "live" && section !== "live" && !isFullscreenPlayerOpen()) {
    clearPlayer();
  }
}

async function loadPublicConfig() {
  if (!apiAvailable) return;

  try {
    const response = await fetch("/api/config");
    const config = await response.json();
    state.defaultServerConfigured = Boolean(config.defaultServerConfigured);
    els.modeTabsContainer.classList.toggle("is-hidden", state.defaultServerConfigured);
    els.serverUrlField.classList.toggle("is-hidden", state.defaultServerConfigured);
    if (state.defaultServerConfigured) {
      setLoginMode("xtream");
      els.serverUrlInput.value = "";
      setStatus("GreenStreem server is configured. Enter your playlist username and password.");
    }
  } catch {
    // Keep the manual server field available if config cannot load.
  }
}

function showSection(section) {
  stopLivePreviewForSection(section);
  state.section = section;
  els.loginView.classList.toggle("is-hidden", section !== "login");
  els.homeView.classList.toggle("is-hidden", section !== "home");
  els.playerView.classList.toggle("is-hidden", section !== "live");
  els.accountView.classList.toggle("is-hidden", section !== "account");
  els.libraryView.classList.toggle("is-hidden", !["movies", "series"].includes(section));
  els.placeholderView.classList.add("is-hidden");
  document.querySelectorAll(".main-nav button").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.section === section);
  });

  if (section === "live") {
    renderCategories();
    renderChannels();
  }

  if (section === "account") {
    renderAccountSettings();
  }

  if (section === "movies" || section === "series") {
    showLibrary(section);
  }
}

function renderAccountSettings() {
  const matchedGuideCount = state.channels.filter((channel) => channel.now && channel.now !== "EPG not connected yet").length;
  els.accountLoginType.textContent = state.sessionId ? state.mode.toUpperCase() : "Not connected";
  els.accountChannelCount.textContent = String(state.channels.length);
  els.accountFavoriteCount.textContent = String(state.favorites.size);
  els.accountStatus.textContent = state.account.status || "Unknown";
  els.accountExpires.textContent = state.account.expires || "Unknown";
  els.accountConnections.textContent =
    state.account.activeConnections || state.account.maxConnections
      ? `${state.account.activeConnections || "0"} / ${state.account.maxConnections || "Unknown"}`
      : "Unknown";
  els.accountPlaybackMode.textContent = state.preferredLiveStreamType === "mpegts" ? "TS First" : "Auto";
  els.accountGuideCount.textContent = String(state.guide.matched ?? matchedGuideCount);
  els.accountGuideStatus.textContent = state.guide.status || (
    matchedGuideCount ? `${matchedGuideCount} channels have current guide data.` : "Guide data has not matched any channels yet."
  );
}

function showLibrary(type) {
  state.activeLibraryType = type;
  const label = type === "movies" ? "Movies" : "TV Series";
  els.libraryEyebrow.textContent = "Xtream Library";
  els.libraryTitle.textContent = label;
  els.librarySearchInput.value = "";

  renderLibrary();
  if (!state.libraries[type].loaded && !state.libraries[type].loading) {
    loadLibrary(type);
  }
}

async function loadLibrary(type) {
  const library = state.libraries[type];
  if (!state.sessionId) {
    els.libraryStatus.textContent = "Log in with Xtream to load this library.";
    return;
  }

  library.loading = true;
  els.libraryStatus.textContent = `Loading ${type === "movies" ? "movies" : "series"}...`;
  renderLibrary();

  try {
    const response = await fetch(`/api/library?session=${encodeURIComponent(state.sessionId)}&type=${encodeURIComponent(type)}`);
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("application/json")) {
      throw new Error("Session needs refreshed. Go back and sign in again.");
    }
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Library failed to load.");

    library.categories = result.categories || ["All"];
    library.items = result.items || [];
    library.loaded = true;
    library.selectedCategory = "All";
    els.libraryStatus.textContent = `Loaded ${library.items.length} ${type === "movies" ? "movies" : "series"}.`;
  } catch (error) {
    els.libraryStatus.textContent = error.message || "Library failed to load.";
  } finally {
    library.loading = false;
    renderLibrary();
  }
}

function filteredLibraryItems() {
  const library = state.libraries[state.activeLibraryType] || { items: [] };
  const search = els.librarySearchInput.value.trim().toLowerCase();
  return library.items.filter((item) => {
    const categoryMatch = library.selectedCategory === "All" || item.category === library.selectedCategory;
    const searchMatch =
      !search ||
      item.title.toLowerCase().includes(search) ||
      item.category.toLowerCase().includes(search) ||
      (item.plot || "").toLowerCase().includes(search);
    return categoryMatch && searchMatch;
  });
}

function renderLibrary() {
  const type = state.activeLibraryType;
  const library = state.libraries[type];
  if (!library) return;

  els.libraryCategorySelect.innerHTML = "";
  (library.categories.length ? library.categories : ["All"]).forEach((category) => {
    const option = document.createElement("option");
    option.value = category;
    option.textContent = category;
    option.selected = category === library.selectedCategory;
    els.libraryCategorySelect.appendChild(option);
  });

  els.libraryGrid.innerHTML = "";
  if (library.loading) {
    els.libraryGrid.appendChild(emptyLibraryMessage("Loading..."));
    return;
  }

  const items = filteredLibraryItems();
  if (!items.length) {
    els.libraryGrid.appendChild(emptyLibraryMessage(library.loaded ? "No items found." : "Library has not loaded yet."));
    return;
  }

  items.slice(0, 300).forEach((item) => {
    els.libraryGrid.appendChild(renderLibraryCard(item));
  });
}

function emptyLibraryMessage(message) {
  const empty = document.createElement("p");
  empty.className = "empty-state";
  empty.textContent = message;
  return empty;
}

function renderLibraryCard(item) {
  const card = document.createElement("button");
  card.className = "library-card";
  card.type = "button";

  const poster = document.createElement("span");
  poster.className = "poster-frame";
  if (item.poster) {
    const img = document.createElement("img");
    img.src = item.poster;
    img.alt = "";
    poster.appendChild(img);
  } else {
    const placeholder = document.createElement("span");
    placeholder.className = "poster-placeholder";
    placeholder.textContent = item.title.slice(0, 1).toUpperCase();
    poster.appendChild(placeholder);
  }

  const body = document.createElement("span");
  body.className = "library-card-body";

  const title = document.createElement("span");
  title.className = "library-card-title";
  title.textContent = item.title;

  const meta = document.createElement("span");
  meta.className = "library-card-meta";
  meta.textContent = [item.year, item.rating, item.category].filter(Boolean).join(" · ");

  const plot = document.createElement("span");
  plot.className = "library-card-plot";
  plot.textContent = item.plot || "";

  body.append(title, meta, plot);
  card.append(poster, body);
  card.addEventListener("click", () => showItemDetails(item));
  return card;
}

function showItemDetails(item) {
  state.selectedLibraryItem = item;
  renderItemDetails(item);
  els.itemModal.classList.remove("is-hidden");
  loadItemDetails(item);
}

function renderItemPoster(item) {
  els.modalPoster.innerHTML = "";
  if (item.poster) {
    const img = document.createElement("img");
    img.src = item.poster;
    img.alt = "";
    els.modalPoster.appendChild(img);
  } else {
    const placeholder = document.createElement("span");
    placeholder.className = "poster-placeholder";
    placeholder.textContent = item.title.slice(0, 1).toUpperCase();
    els.modalPoster.appendChild(placeholder);
  }
}

function renderItemDetails(item) {
  renderItemPoster(item);
  els.modalCategory.textContent = item.category || "Library";
  els.modalTitle.textContent = item.title;
  els.modalMeta.textContent = [item.year, item.rating, item.genre || item.category, item.duration].filter(Boolean).join(" · ");
  els.modalPlot.textContent = item.plot || "Loading description...";
  els.playItemButton.disabled = item.type !== "movies";
  els.playItemButton.textContent = item.type === "movies" ? "Play" : "Episodes Soon";
}

async function loadItemDetails(item) {
  if (!state.sessionId || item.type !== "movies") {
    els.modalPlot.textContent = item.plot || "No description available.";
    return;
  }

  try {
    const response = await fetch(
      `/api/item?session=${encodeURIComponent(state.sessionId)}&type=${encodeURIComponent(item.type)}&id=${encodeURIComponent(item.id)}`,
    );
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Details failed to load.");
    const details = result.details || {};
    Object.assign(item, Object.fromEntries(Object.entries(details).filter(([, value]) => value)));
    if (state.selectedLibraryItem === item) {
      renderItemDetails(item);
      els.modalPlot.textContent = item.plot || (item.debugFields ? `No description available. Fields: ${item.debugFields}` : "No description available.");
    }
  } catch {
    if (state.selectedLibraryItem === item) {
      els.modalPlot.textContent = item.plot || "No description available.";
    }
  }
}

function closeItemDetails() {
  els.itemModal.classList.add("is-hidden");
}

function activeVideo() {
  return state.playbackVideo || els.videoPlayer;
}

function isFullscreenPlayerOpen() {
  return !els.fullscreenPlayer.classList.contains("is-hidden");
}

function setPlaybackStatus(message) {
  if (isFullscreenPlayerOpen()) {
    els.fullscreenStatus.textContent = message;
  } else {
    els.nowTime.textContent = message;
  }
}

async function buildStreamReport() {
  if (!state.activeChannel) {
    els.streamReport.textContent = "Choose a channel first.";
    return;
  }

  const video = els.videoPlayer;
  const parts = [
    `Channel: ${state.activeChannel.name}`,
    `Browser: ${video.paused ? "paused" : "playing"}, time ${Math.floor(video.currentTime || 0)}s, ready ${video.readyState}/4`,
    video.muted || video.volume === 0 ? "Audio: muted or volume is zero" : "Audio: browser volume is on",
  ];

  try {
    const response = await fetch(`/api/diagnostics?session=${encodeURIComponent(state.sessionId)}`);
    const result = await response.json();
    const latestResponse = [...(result.events || [])].reverse().find((event) => event.event === "response" || event.status);
    if (latestResponse) {
      parts.push(
        `Provider: HTTP ${latestResponse.status || "unknown"} ${latestResponse.contentType || ""} ${latestResponse.host ? `from ${latestResponse.host}` : ""}`.trim(),
      );
    }
  } catch {
    parts.push("Provider: diagnostics unavailable");
  }

  if (!video.paused && video.currentTime > 0 && !video.muted && video.volume > 0) {
    parts.push("If video moves but there is no sound, suspect that channel feed or browser-incompatible audio codec.");
  }

  els.streamReport.textContent = parts.join(" | ");
}

function openFullscreenPlayer(item) {
  const meta = [item.year, item.rating, item.category].filter(Boolean).join(" · ") || "Movie";
  state.playbackVideo = els.fullscreenVideoPlayer;
  els.fullscreenTitle.textContent = item.title;
  els.fullscreenMeta.textContent = meta;
  els.fullscreenStatus.textContent = "Loading movie...";
  els.fullscreenPlayer.classList.remove("is-hidden");
  els.fullscreenPlayer.focus();
  showFullscreenControls();

  const requestFullscreen = els.fullscreenPlayer.requestFullscreen?.bind(els.fullscreenPlayer);
  if (requestFullscreen) {
    requestFullscreen().catch(() => {});
  }
}

function closeFullscreenPlayer({ exitFullscreen = true } = {}) {
  if (!isFullscreenPlayerOpen()) return;
  window.clearTimeout(state.fullscreenControlsTimer);
  state.fullscreenControlsTimer = null;
  clearPlayer();
  els.fullscreenPlayer.classList.add("is-hidden");
  els.fullscreenPlayer.classList.remove("is-controls-visible");
  state.playbackVideo = els.videoPlayer;
  els.fullscreenStatus.textContent = "Loading...";

  if (exitFullscreen && document.fullscreenElement) {
    document.exitFullscreen().catch(() => {});
  }
}

function showFullscreenControls() {
  if (!isFullscreenPlayerOpen()) return;
  els.fullscreenPlayer.classList.add("is-controls-visible");
  window.clearTimeout(state.fullscreenControlsTimer);
  state.fullscreenControlsTimer = window.setTimeout(() => {
    els.fullscreenPlayer.classList.remove("is-controls-visible");
  }, 1800);
}

function playLibraryItem(item) {
  if (item.type !== "movies") {
    els.libraryStatus.textContent = "Series episode browsing is next.";
    return;
  }

  const playUrl = `/api/vod?session=${encodeURIComponent(state.sessionId)}&id=${encodeURIComponent(item.id)}&ext=${encodeURIComponent(item.container || "mp4")}`;
  state.activeChannelIndex = -1;
  state.activeChannel = null;
  els.currentCategoryLabel.textContent = item.category || "Movies";
  els.currentChannelTitle.textContent = item.title;
  els.nowTitle.textContent = item.title;
  els.nextTitle.textContent = [item.year, item.rating, item.category].filter(Boolean).join(" · ") || "Movie";
  closeItemDetails();
  openFullscreenPlayer(item);
  loadStream(playUrl, item.container === "m3u8" ? "hls" : "file");
}

function setLoginMode(mode) {
  state.mode = mode;
  els.modeTabs.forEach((tab) => tab.classList.toggle("is-active", tab.dataset.mode === mode));
  els.xtreamFields.classList.toggle("is-hidden", mode !== "xtream");
  els.m3uFields.classList.toggle("is-hidden", mode !== "m3u");
}

function categories() {
  const names = new Set(["All Channels", "Only Favorites"]);
  state.channels.forEach((channel) => names.add(channel.category || "Uncategorized"));
  return [...names].sort((a, b) => {
      if (a === "All Channels") return -1;
      if (b === "All Channels") return 1;
      if (a === "Only Favorites") return -1;
      if (b === "Only Favorites") return 1;
      return a.localeCompare(b);
  });
}

function visibleChannels() {
  const search = els.channelSearchInput.value.trim().toLowerCase();
  return state.channels.filter((channel, index) => {
    const favorite = state.favorites.has(channel.name);
    const categoryMatch =
      state.activeCategory === "All Channels" ||
      state.activeCategory === channel.category ||
      state.activeCategory === "Only Favorites";
    const favoriteMatch = !state.favoritesOnly && state.activeCategory !== "Only Favorites" ? true : favorite;
    const searchMatch = !search || channel.name.toLowerCase().includes(search);
    return categoryMatch && favoriteMatch && searchMatch;
  });
}

function renderCategories() {
  const search = els.categorySearchInput.value.trim().toLowerCase();
  els.categoryList.innerHTML = "";

  categories()
    .filter((category) => !search || category.toLowerCase().includes(search))
    .forEach((category) => {
      const button = document.createElement("button");
      button.className = "category-item";
      button.classList.toggle("is-active", category === state.activeCategory);
      button.type = "button";
      button.textContent = category;
      button.addEventListener("click", () => {
        state.activeCategory = category;
        state.favoritesOnly = category === "Only Favorites";
        els.favoritesOnlyButton.classList.toggle("is-active", state.favoritesOnly);
        els.currentCategoryLabel.textContent = category;
        closeDrawer();
        renderCategories();
        renderChannels();
      });
      els.categoryList.appendChild(button);
    });
}

function renderChannels({ preserveScroll = false } = {}) {
  const previousScrollTop = preserveScroll ? els.channelList.scrollTop : 0;
  els.channelList.innerHTML = "";
  const list = visibleChannels();

  if (!list.length) {
    const empty = document.createElement("p");
    empty.className = "empty-state";
    empty.textContent = "No channels found.";
    els.channelList.appendChild(empty);
    return;
  }

  list.forEach((channel) => {
    const originalIndex = state.channels.indexOf(channel);
    const row = document.createElement("button");
    row.className = "channel-row";
    row.classList.toggle("is-active", originalIndex === state.activeChannelIndex);
    row.type = "button";

    const number = document.createElement("span");
    number.className = "channel-number";
    number.textContent = String(originalIndex + 1);

    const logo = channel.logo ? document.createElement("img") : document.createElement("span");
    logo.className = "channel-logo";
    if (channel.logo) {
      logo.src = channel.logo;
      logo.alt = "";
    } else {
      logo.setAttribute("aria-hidden", "true");
    }

    const info = document.createElement("span");
    info.className = "channel-info";

    const name = document.createElement("span");
    name.className = "channel-name";
    name.textContent = channel.name;

    const program = document.createElement("span");
    program.className = "channel-program";
    program.textContent = channel.now && channel.now !== "EPG not connected yet" ? channel.now : "No guide information";

    const next = document.createElement("span");
    next.className = "channel-next";
    next.textContent = channel.next || "";

    info.append(name, program, next);

    const favorite = document.createElement("span");
    favorite.className = "favorite-button";
    favorite.classList.toggle("is-favorite", state.favorites.has(channel.name));
    favorite.setAttribute("aria-label", "Favorite");
    favorite.textContent = "☆";

    row.append(number, logo, info, favorite);

    row.addEventListener("mousedown", (event) => {
      event.preventDefault();
    });

    row.addEventListener("click", (event) => {
      if (event.target.classList.contains("favorite-button")) {
        toggleFavorite(channel.name);
        return;
      }
      playChannel(originalIndex);
    });

    els.channelList.appendChild(row);
  });

  if (preserveScroll) {
    els.channelList.scrollTop = previousScrollTop;
  }
}

function playChannel(index) {
  const channel = state.channels[index];
  state.playbackVideo = els.videoPlayer;
  state.activeChannelIndex = index;
  els.streamReport.textContent = "";
  els.currentChannelTitle.textContent = channel.name;
  els.currentCategoryLabel.textContent = channel.category || "Uncategorized";
  els.nowTitle.textContent = channel.now || "EPG not connected yet";
  els.nextTitle.textContent = channel.next || "No upcoming program loaded.";
  const streamUrl = channel.playUrl || channel.url;
  const hasStream = channel.hasStream || Boolean(streamUrl);
  els.nowTime.textContent = hasStream ? "Loading stream..." : "Demo channel has no live stream URL yet.";
  state.activeChannel = channel;
  state.triedFallback = false;
  state.pendingTsPreference = false;

  if (hasStream) {
    const shouldPreferTs =
      state.preferredLiveStreamType === "mpegts" &&
      channel.fallbackPlayUrl &&
      channel.fallbackStreamType === "mpegts";

    if (shouldPreferTs) {
      els.nowTime.textContent = "Using learned TS playback path...";
      state.triedFallback = true;
      loadStream(channel.fallbackPlayUrl, channel.fallbackStreamType);
    } else {
      loadStream(streamUrl, channel.streamType || channel.url || "");
    }
  } else {
    clearPlayer();
  }

  renderChannels({ preserveScroll: true });
}

function clearPlayer() {
  if (state.hls) {
    state.hls.destroy();
    state.hls = null;
  }
  if (state.mpegts) {
    state.mpegts.destroy();
    state.mpegts = null;
  }
  [els.videoPlayer, els.fullscreenVideoPlayer].forEach((video) => {
    video.pause();
    video.removeAttribute("src");
    video.load();
  });
}

function loadStream(playUrl, streamType) {
  clearPlayer();
  const video = activeVideo();
  const looksLikeHls = streamType === "hls" || /\.m3u8($|\?)/i.test(playUrl);

  if (looksLikeHls && window.Hls && window.Hls.isSupported()) {
    state.hls = new Hls({ lowLatencyMode: true });
    state.hls.on(Hls.Events.MEDIA_ATTACHED, () => {
      setPlaybackStatus("Opening HLS stream...");
    });
    state.hls.on(Hls.Events.ERROR, (_event, data) => {
      const issue = data.details || data.type;
      const shouldTryFallback =
        data.details === Hls.ErrorDetails.FRAG_LOAD_ERROR ||
        data.type === Hls.ErrorTypes.MEDIA_ERROR ||
        /mse|decode|buffer/i.test(issue || "");

      setPlaybackStatus(`Stream issue: ${issue}`);
      showLatestDiagnostics(issue);
      if (shouldTryFallback && tryFallbackStream(issue)) {
        return;
      }
      if (data.fatal) {
        if (tryFallbackStream(issue)) return;
        setPlaybackStatus(`Playback failed: ${issue}`);
        state.hls.destroy();
        state.hls = null;
      }
    });
    state.hls.on(Hls.Events.LEVEL_LOADED, () => {
      setPlaybackStatus("HLS playlist loaded. Fetching video segments...");
    });
    state.hls.on(Hls.Events.FRAG_LOADED, () => {
      setPlaybackStatus("Video segment loaded. Buffering...");
    });
    state.hls.on(Hls.Events.BUFFER_APPENDED, () => {
      setPlaybackStatus("Video buffered. Starting playback...");
    });
    state.hls.on(Hls.Events.MANIFEST_PARSED, () => {
      setPlaybackStatus("HLS stream ready.");
      attemptPlay();
    });
    state.hls.loadSource(playUrl);
    state.hls.attachMedia(video);
    return;
  }

  if (looksLikeHls && video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = playUrl;
    setPlaybackStatus("Native HLS stream ready.");
    attemptPlay();
    return;
  }

  if (streamType === "mpegts" && window.mpegts && window.mpegts.getFeatureList().mseLivePlayback) {
    const fallbackTrial = state.pendingTsPreference;
    state.mpegts = mpegts.createPlayer({
      type: "mpegts",
      isLive: true,
      url: playUrl,
    });
    state.mpegts.on(mpegts.Events.ERROR, (_type, detail) => {
      setPlaybackStatus(`TS playback failed: ${detail || "stream error"}`);
      showLatestDiagnostics(detail || "mpegts error");
    });
    state.mpegts.attachMediaElement(video);
    state.mpegts.load();
    setPlaybackStatus(fallbackTrial ? "Trying direct TS stream fallback..." : "Opening TS stream...");
    attemptPlay();
    return;
  }

  video.src = playUrl;
  setPlaybackStatus(looksLikeHls
    ? "HLS helper did not load. Refresh the page and try again."
    : "Trying direct stream playback. Some .ts streams need conversion.");
  attemptPlay();
}

function tryFallbackStream(reason) {
  const channel = state.activeChannel;
  if (!channel || state.triedFallback || !channel.fallbackPlayUrl) return false;

  state.triedFallback = true;
  state.pendingTsPreference = true;
  setPlaybackStatus(`${reason}. Trying TS fallback...`);
  if (state.hls) {
    state.hls.destroy();
    state.hls = null;
  }
  loadStream(channel.fallbackPlayUrl, channel.fallbackStreamType || "mpegts");
  return true;
}

function attemptPlay() {
  activeVideo().play().catch(() => {
    setPlaybackStatus("Stream loaded. Press play in the video window.");
  });
}

function attachVideoEvents(video) {
  video.addEventListener("playing", () => {
    if (state.pendingTsPreference && state.activeChannel?.fallbackStreamType === "mpegts") {
      state.preferredLiveStreamType = "mpegts";
      localStorage.setItem("greenstreem:preferredLiveStreamType", "mpegts");
      state.pendingTsPreference = false;
    }
    setPlaybackStatus("Playing.");
  });

  video.addEventListener("waiting", () => {
    setPlaybackStatus("Buffering video...");
  });

  video.addEventListener("stalled", () => {
    setPlaybackStatus("Stream stalled while loading video data.");
  });

  video.addEventListener("error", () => {
    const error = video.error;
    const message =
      error?.code === MediaError.MEDIA_ERR_DECODE
        ? "Video codec is not supported by this browser."
        : error?.code === MediaError.MEDIA_ERR_NETWORK
          ? "Network error while loading stream."
          : "Browser could not play this stream.";
    setPlaybackStatus(message);
    showLatestDiagnostics(message);
  });
}

attachVideoEvents(els.videoPlayer);
attachVideoEvents(els.fullscreenVideoPlayer);

async function showLatestDiagnostics(prefix) {
  if (!state.sessionId || !apiAvailable) return;

  try {
    const response = await fetch(`/api/diagnostics?session=${encodeURIComponent(state.sessionId)}`);
    const result = await response.json();
    const latest = [...(result.events || [])].reverse().find((event) => event.status || event.reason || event.details);
    if (!latest) return;

    const bits = [
      prefix,
      latest.status ? `HTTP ${latest.status}` : "",
      latest.reason || latest.details || "",
      latest.host ? `from ${latest.host}` : "",
      latest.type ? latest.type : "",
    ].filter(Boolean);
    setPlaybackStatus(bits.join(" · "));
  } catch {
    // Diagnostics are helpful but should never interrupt playback.
  }
}

function toggleFavorite(name) {
  if (state.favorites.has(name)) {
    state.favorites.delete(name);
  } else {
    state.favorites.add(name);
  }
  localStorage.setItem("greenstreem:favorites", JSON.stringify([...state.favorites]));
  renderChannels();
  renderAccountSettings();
}

function parseM3u(text) {
  const lines = text.split(/\r?\n/);
  const channels = [];

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i].trim();
    if (!line.startsWith("#EXTINF")) continue;

    const nextUrl = (lines[i + 1] || "").trim();
    const name = line.split(",").pop()?.trim() || "Untitled Channel";
    const category = getAttribute(line, "group-title") || "Uncategorized";
    const logo = getAttribute(line, "tvg-logo") || "";

    if (nextUrl && !nextUrl.startsWith("#")) {
      channels.push({ name, category, logo, url: nextUrl, now: "EPG not connected yet" });
    }
  }

  return channels;
}

function getAttribute(line, attribute) {
  const match = line.match(new RegExp(`${attribute}="([^"]*)"`));
  return match ? match[1] : "";
}

function openDrawer() {
  renderCategories();
  els.categoryDrawer.classList.add("is-open");
  els.drawerScrim.classList.add("is-open");
}

function closeDrawer() {
  els.categoryDrawer.classList.remove("is-open");
  els.drawerScrim.classList.remove("is-open");
}

function updateActiveGuidePanel() {
  if (state.activeChannelIndex < 0) return;
  const channel = state.channels[state.activeChannelIndex];
  if (!channel) return;
  els.nowTitle.textContent = channel.now || "EPG not connected yet";
  els.nextTitle.textContent = channel.next || "No upcoming program loaded.";
}

function stopGuidePolling() {
  if (state.guidePollTimer) {
    clearTimeout(state.guidePollTimer);
    state.guidePollTimer = null;
  }
}

async function refreshSessionData() {
  if (!state.sessionId || !apiAvailable) return;

  try {
    const response = await fetch(`/api/session?session=${encodeURIComponent(state.sessionId)}`);
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Session refresh failed.");

    state.channels = result.channels.length ? result.channels : state.channels;
    state.account = result.account || state.account;
    state.guide = result.guide || state.guide;

    if (state.section === "live") {
      renderCategories();
      renderChannels();
    }
    if (state.section === "account") {
      renderAccountSettings();
    }
    updateActiveGuidePanel();

    if (state.guide.loading) {
      state.guidePollTimer = setTimeout(refreshSessionData, 1200);
    } else {
      state.guidePollTimer = null;
    }
  } catch {
    state.guidePollTimer = null;
  }
}

function startGuidePolling() {
  stopGuidePolling();
  if (state.guide?.loading) {
    state.guidePollTimer = setTimeout(refreshSessionData, 700);
  }
}

els.modeTabs.forEach((tab) => {
  tab.addEventListener("click", () => setLoginMode(tab.dataset.mode));
});

els.loginForm.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!apiAvailable) {
    setStatus("Open this through the Python backend for real login. Demo mode works from file.");
    showSection("home");
    return;
  }

  setStatus("Loading your playlist through GreenStreem backend...");

  const payload =
    state.mode === "m3u"
      ? {
          mode: "m3u",
          m3uUrl: document.querySelector("#m3uUrlInput").value.trim(),
          epgUrl: document.querySelector("#epgUrlInput").value.trim(),
        }
      : {
          mode: "xtream",
          serverUrl: els.serverUrlInput.value.trim(),
          username: document.querySelector("#usernameInput").value.trim(),
          password: document.querySelector("#passwordInput").value,
        };

  try {
    const response = await fetch("/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.error || "Login failed.");
    }
    state.sessionId = result.sessionId;
    state.channels = result.channels.length ? result.channels : [...demoChannels];
    state.account = result.account || {};
    state.guide = result.guide || {};
    state.activeCategory = "All Channels";
    state.activeChannelIndex = -1;
    state.preferredLiveStreamType = localStorage.getItem("greenstreem:preferredLiveStreamType") || "auto";
    setStatus(state.guide.loading ? `Loaded ${state.channels.length} channels. Guide is still loading...` : `Loaded ${state.channels.length} channels.`);
    showSection("home");
    startGuidePolling();
  } catch (error) {
    setStatus(error.message || "Could not load the playlist.");
  }
});

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-section]");
  if (!button) return;
  event.preventDefault();
  showSection(button.dataset.section);
});

els.openCategoriesButton.addEventListener("click", openDrawer);
els.closeCategoriesButton.addEventListener("click", closeDrawer);
els.drawerScrim.addEventListener("click", closeDrawer);
els.categorySearchInput.addEventListener("input", renderCategories);
els.channelSearchInput.addEventListener("input", renderChannels);
els.librarySearchInput.addEventListener("input", renderLibrary);
els.libraryCategorySelect.addEventListener("change", () => {
  const library = state.libraries[state.activeLibraryType];
  if (!library) return;
  library.selectedCategory = els.libraryCategorySelect.value;
  renderLibrary();
});
els.closeItemModalButton.addEventListener("click", closeItemDetails);
els.modalBackButton.addEventListener("click", closeItemDetails);
els.playItemButton.addEventListener("click", () => {
  if (state.selectedLibraryItem) {
    playLibraryItem(state.selectedLibraryItem);
  }
});
els.fullscreenPlayer.addEventListener("mousemove", showFullscreenControls);
els.fullscreenPlayer.addEventListener("pointerdown", showFullscreenControls);
els.fullscreenPlayer.addEventListener("focusin", showFullscreenControls);
els.closeFullscreenPlayerButton.addEventListener("click", () => closeFullscreenPlayer());

els.searchButton.addEventListener("click", () => {
  showSection("live");
  els.channelSearchInput.focus();
});

els.favoritesOnlyButton.addEventListener("click", () => {
  state.favoritesOnly = !state.favoritesOnly;
  els.favoritesOnlyButton.classList.toggle("is-active", state.favoritesOnly);
  renderChannels();
});

els.streamReportButton.addEventListener("click", buildStreamReport);

els.resetPlaybackButton.addEventListener("click", () => {
  state.preferredLiveStreamType = "auto";
  state.pendingTsPreference = false;
  localStorage.removeItem("greenstreem:preferredLiveStreamType");
  els.nowTime.textContent = "Playback learning reset. Next channel will try HLS first.";
  renderAccountSettings();
});

els.preferAutoButton.addEventListener("click", () => {
  state.preferredLiveStreamType = "auto";
  localStorage.removeItem("greenstreem:preferredLiveStreamType");
  renderAccountSettings();
});

els.preferTsButton.addEventListener("click", () => {
  state.preferredLiveStreamType = "mpegts";
  localStorage.setItem("greenstreem:preferredLiveStreamType", "mpegts");
  renderAccountSettings();
});

els.clearFavoritesButton.addEventListener("click", () => {
  state.favorites.clear();
  localStorage.setItem("greenstreem:favorites", "[]");
  renderChannels();
  renderAccountSettings();
});

els.logoutButton.addEventListener("click", () => {
  clearPlayer();
  stopGuidePolling();
  state.sessionId = "";
  state.account = {};
  state.guide = {};
  state.channels = [...demoChannels];
  state.activeChannelIndex = -1;
  state.activeChannel = null;
  els.currentChannelTitle.textContent = "Choose a channel";
  els.currentCategoryLabel.textContent = "All Channels";
  els.nowTitle.textContent = "No program selected";
  els.nextTitle.textContent = "Guide data will appear here when connected.";
  els.nowTime.textContent = "Idle.";
  setStatus("Signed out.");
  showSection("login");
});

els.fullscreenButton.addEventListener("click", () => {
  if (els.videoPlayer.requestFullscreen) {
    els.videoPlayer.requestFullscreen();
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && isFullscreenPlayerOpen()) {
    closeFullscreenPlayer();
  }
});

document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement && isFullscreenPlayerOpen()) {
    closeFullscreenPlayer({ exitFullscreen: false });
  }
});

showSection("login");
loadPublicConfig();
