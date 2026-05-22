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
  channels: [...demoChannels],
  activeCategory: "All Channels",
  activeChannelIndex: -1,
  favoritesOnly: false,
  favorites: new Set(JSON.parse(localStorage.getItem("greenstreem:favorites") || "[]")),
  hls: null,
  mpegts: null,
  activeChannel: null,
  triedFallback: false,
};

const els = {
  loginView: document.querySelector("#loginView"),
  homeView: document.querySelector("#homeView"),
  playerView: document.querySelector("#playerView"),
  placeholderView: document.querySelector("#placeholderView"),
  loginForm: document.querySelector("#loginForm"),
  modeTabs: document.querySelectorAll(".mode-tab"),
  xtreamFields: document.querySelector("#xtreamFields"),
  m3uFields: document.querySelector("#m3uFields"),
  demoButton: document.querySelector("#demoButton"),
  channelList: document.querySelector("#channelList"),
  categoryList: document.querySelector("#categoryList"),
  channelSearchInput: document.querySelector("#channelSearchInput"),
  categorySearchInput: document.querySelector("#categorySearchInput"),
  currentCategoryLabel: document.querySelector("#currentCategoryLabel"),
  currentChannelTitle: document.querySelector("#currentChannelTitle"),
  nowTitle: document.querySelector("#nowTitle"),
  nowTime: document.querySelector("#nowTime"),
  videoPlayer: document.querySelector("#videoPlayer"),
  categoryDrawer: document.querySelector("#categoryDrawer"),
  drawerScrim: document.querySelector("#drawerScrim"),
  openCategoriesButton: document.querySelector("#openCategoriesButton"),
  closeCategoriesButton: document.querySelector("#closeCategoriesButton"),
  fullscreenButton: document.querySelector("#fullscreenButton"),
  searchButton: document.querySelector("#searchButton"),
  favoritesOnlyButton: document.querySelector("#favoritesOnlyButton"),
  loginStatus: document.querySelector("#loginStatus"),
  placeholderTitle: document.querySelector("#placeholderTitle"),
  placeholderCopy: document.querySelector("#placeholderCopy"),
};

const apiAvailable = window.location.protocol !== "file:";

function setStatus(message) {
  els.loginStatus.textContent = message;
}

function showSection(section) {
  state.section = section;
  els.loginView.classList.toggle("is-hidden", section !== "login");
  els.homeView.classList.toggle("is-hidden", section !== "home");
  els.playerView.classList.toggle("is-hidden", section !== "live");
  els.placeholderView.classList.toggle("is-hidden", !["movies", "series", "account"].includes(section));

  if (section === "live") {
    renderCategories();
    renderChannels();
  }

  if (section === "movies" || section === "series" || section === "account") {
    const label = section === "movies" ? "Movies" : section === "series" ? "TV Series" : "Account Info";
    els.placeholderTitle.textContent = label;
    els.placeholderCopy.textContent = `${label} is stubbed in so the flow is ready for the next pass.`;
  }
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

function renderChannels() {
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

    const name = document.createElement("span");
    name.className = "channel-name";
    name.textContent = channel.name;

    const favorite = document.createElement("span");
    favorite.className = "favorite-button";
    favorite.classList.toggle("is-favorite", state.favorites.has(channel.name));
    favorite.setAttribute("aria-label", "Favorite");
    favorite.textContent = "☆";

    row.append(number, logo, name, favorite);

    row.addEventListener("click", (event) => {
      if (event.target.classList.contains("favorite-button")) {
        toggleFavorite(channel.name);
        return;
      }
      playChannel(originalIndex);
    });

    els.channelList.appendChild(row);
  });
}

function playChannel(index) {
  const channel = state.channels[index];
  state.activeChannelIndex = index;
  els.currentChannelTitle.textContent = channel.name;
  els.currentCategoryLabel.textContent = channel.category || "Uncategorized";
  els.nowTitle.textContent = channel.now || "EPG not connected yet";
  const streamUrl = channel.playUrl || channel.url;
  const hasStream = channel.hasStream || Boolean(streamUrl);
  els.nowTime.textContent = hasStream ? "Loading stream..." : "Demo channel has no live stream URL yet.";
  state.activeChannel = channel;
  state.triedFallback = false;

  if (hasStream) {
    loadStream(streamUrl, channel.streamType || channel.url || "");
  } else {
    clearPlayer();
  }

  renderChannels();
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
  els.videoPlayer.pause();
  els.videoPlayer.removeAttribute("src");
  els.videoPlayer.load();
}

function loadStream(playUrl, streamType) {
  clearPlayer();
  const looksLikeHls = streamType === "hls" || /\.m3u8($|\?)/i.test(playUrl);

  if (looksLikeHls && window.Hls && window.Hls.isSupported()) {
    state.hls = new Hls({ lowLatencyMode: true });
    state.hls.on(Hls.Events.MEDIA_ATTACHED, () => {
      els.nowTime.textContent = "Opening HLS stream...";
    });
    state.hls.on(Hls.Events.ERROR, (_event, data) => {
      els.nowTime.textContent = `Stream issue: ${data.details || data.type}`;
      showLatestDiagnostics(data.details || data.type);
      if (data.fatal) {
        if (tryFallbackStream(data.details || data.type)) return;
        els.nowTime.textContent = `Playback failed: ${data.details || data.type}`;
        state.hls.destroy();
        state.hls = null;
      }
    });
    state.hls.on(Hls.Events.LEVEL_LOADED, () => {
      els.nowTime.textContent = "HLS playlist loaded. Fetching video segments...";
    });
    state.hls.on(Hls.Events.FRAG_LOADED, () => {
      els.nowTime.textContent = "Video segment loaded. Buffering...";
    });
    state.hls.on(Hls.Events.BUFFER_APPENDED, () => {
      els.nowTime.textContent = "Video buffered. Starting playback...";
    });
    state.hls.on(Hls.Events.MANIFEST_PARSED, () => {
      els.nowTime.textContent = "HLS stream ready.";
      attemptPlay();
    });
    state.hls.loadSource(playUrl);
    state.hls.attachMedia(els.videoPlayer);
    return;
  }

  if (looksLikeHls && els.videoPlayer.canPlayType("application/vnd.apple.mpegurl")) {
    els.videoPlayer.src = playUrl;
    els.nowTime.textContent = "Native HLS stream ready.";
    attemptPlay();
    return;
  }

  if (streamType === "mpegts" && window.mpegts && window.mpegts.getFeatureList().mseLivePlayback) {
    state.mpegts = mpegts.createPlayer({
      type: "mpegts",
      isLive: true,
      url: playUrl,
    });
    state.mpegts.on(mpegts.Events.ERROR, (_type, detail) => {
      els.nowTime.textContent = `TS playback failed: ${detail || "stream error"}`;
      showLatestDiagnostics(detail || "mpegts error");
    });
    state.mpegts.attachMediaElement(els.videoPlayer);
    state.mpegts.load();
    els.nowTime.textContent = "Trying direct TS stream fallback...";
    attemptPlay();
    return;
  }

  els.videoPlayer.src = playUrl;
  els.nowTime.textContent = looksLikeHls
    ? "HLS helper did not load. Refresh the page and try again."
    : "Trying direct stream playback. Some .ts streams need conversion.";
  attemptPlay();
}

function tryFallbackStream(reason) {
  const channel = state.activeChannel;
  if (!channel || state.triedFallback || !channel.fallbackPlayUrl) return false;

  state.triedFallback = true;
  els.nowTime.textContent = `${reason}. Trying TS fallback...`;
  if (state.hls) {
    state.hls.destroy();
    state.hls = null;
  }
  loadStream(channel.fallbackPlayUrl, channel.fallbackStreamType || "mpegts");
  return true;
}

function attemptPlay() {
  els.videoPlayer.play().catch(() => {
    els.nowTime.textContent = "Stream loaded. Press play in the video window.";
  });
}

els.videoPlayer.addEventListener("playing", () => {
  els.nowTime.textContent = "Playing.";
});

els.videoPlayer.addEventListener("waiting", () => {
  els.nowTime.textContent = "Buffering video...";
});

els.videoPlayer.addEventListener("stalled", () => {
  els.nowTime.textContent = "Stream stalled while loading video data.";
});

els.videoPlayer.addEventListener("error", () => {
  const error = els.videoPlayer.error;
  const message =
    error?.code === MediaError.MEDIA_ERR_DECODE
      ? "Video codec is not supported by this browser."
      : error?.code === MediaError.MEDIA_ERR_NETWORK
        ? "Network error while loading stream."
        : "Browser could not play this stream.";
  els.nowTime.textContent = message;
  showLatestDiagnostics(message);
});

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
    els.nowTime.textContent = bits.join(" · ");
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
          serverUrl: document.querySelector("#serverUrlInput").value.trim(),
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
    state.activeCategory = "All Channels";
    state.activeChannelIndex = -1;
    setStatus(`Loaded ${state.channels.length} channels.`);
    showSection("home");
  } catch (error) {
    setStatus(error.message || "Could not load the playlist.");
  }
});

els.demoButton.addEventListener("click", () => {
  state.channels = [...demoChannels];
  showSection("home");
});

document.querySelectorAll("[data-section]").forEach((button) => {
  button.addEventListener("click", () => showSection(button.dataset.section));
});

els.openCategoriesButton.addEventListener("click", openDrawer);
els.closeCategoriesButton.addEventListener("click", closeDrawer);
els.drawerScrim.addEventListener("click", closeDrawer);
els.categorySearchInput.addEventListener("input", renderCategories);
els.channelSearchInput.addEventListener("input", renderChannels);

els.searchButton.addEventListener("click", () => {
  showSection("live");
  els.channelSearchInput.focus();
});

els.favoritesOnlyButton.addEventListener("click", () => {
  state.favoritesOnly = !state.favoritesOnly;
  els.favoritesOnlyButton.classList.toggle("is-active", state.favoritesOnly);
  renderChannels();
});

els.fullscreenButton.addEventListener("click", () => {
  if (els.videoPlayer.requestFullscreen) {
    els.videoPlayer.requestFullscreen();
  }
});

showSection("login");
