<template>
  <svg
    v-if="!moving"
    viewBox="0 0 24 24"
    aria-hidden="true"
    focusable="false"
    xmlns="http://www.w3.org/2000/svg"
  >
    <g transform="matrix(0.048 0 0 0.048 1.8 0.16)">
      <g transform="translate(0.8 0.9)">
        <g transform="translate(0 32)">
          <path :d="LARGE_STAR" fill="#2f86bd" transform="translate(0 35)" />
          <path
            :d="SMALL_STAR"
            fill="#2f86bd"
            transform="matrix(0.95 0 0 0.95 22 -278)"
          />
        </g>
      </g>
    </g>
  </svg>
  <svg
    v-else
    viewBox="0 0 24 24"
    aria-hidden="true"
    focusable="false"
    xmlns="http://www.w3.org/2000/svg"
  >
    <defs>
      <linearGradient
        v-for="tide in TIDES"
        :id="`${uid}-${tide.name}`"
        :key="tide.name"
        x1="0"
        y1="0"
        x2="0"
        y2="1"
      >
        <stop offset="0" :stop-color="tide.top" />
        <stop offset="1" :stop-color="tide.bottom" />
      </linearGradient>
      <!-- The small star centred on the origin, placed by its orbit. -->
      <path
        :id="`${uid}-small`"
        :d="SMALL_STAR"
        transform="translate(-20.58 -6.14) matrix(0.048 0 0 0.048 1.8384 1.7392) matrix(0.95 0 0 0.95 22 -278)"
      />
      <!-- The stars' shapes. The small star is drawn twice: faint under the
           large star on the far half of the orbit, and over it with a black
           (cut-out) rim on the near half. SMIL keeps both on one clock. -->
      <mask
        :id="`${uid}-mask`"
        maskUnits="userSpaceOnUse"
        x="-2"
        y="-2"
        width="28"
        height="28"
      >
        <template v-for="copy in COPIES" :key="copy.name">
          <path
            v-if="copy.name === 'large'"
            :d="LARGE_STAR"
            fill="white"
            transform="matrix(0.048 0 0 0.048 1.8384 1.7392) translate(0 35)"
          />
          <use
            v-else
            :href="`#${uid}-small`"
            v-bind="copy.attrs"
            stroke-width="28"
            stroke-linejoin="round"
            paint-order="stroke"
          >
            <animateTransform
              attributeName="transform"
              type="translate"
              :values="ORBIT.translate"
              v-bind="LOOP"
            />
            <animateTransform
              attributeName="transform"
              type="scale"
              :values="ORBIT.scale"
              additive="sum"
              v-bind="LOOP"
            />
            <animate
              attributeName="visibility"
              :values="copy.visibility"
              keyTimes="0;0.5"
              calcMode="discrete"
              v-bind="LOOP"
            />
          </use>
        </template>
      </mask>
    </defs>
    <!-- One colour field cut out by the stars: a gold tide rises with waves,
         then a blue tide rises over it, taking turns without a seam. -->
    <g :mask="`url(#${uid}-mask)`">
      <rect x="-2" y="-2" width="28" height="28" fill="#2f86bd" />
      <g v-for="tide in TIDES" :key="tide.name">
        <animateTransform
          attributeName="transform"
          type="translate"
          values="0 26;0 26;0 -3;0 -3"
          :keyTimes="tide.rise"
          dur="5.6s"
          repeatCount="indefinite"
        />
        <path :fill="`url(#${uid}-${tide.name})`" :d="WAVE">
          <animateTransform
            attributeName="transform"
            type="translate"
            :values="tide.drift"
            dur="1.2s"
            repeatCount="indefinite"
          />
        </path>
      </g>
    </g>
  </svg>
</template>

<script lang="ts">
import { ref } from "vue";

let logoCount = 0;

// SMIL ignores the reduced-motion media query, so follow it here, including
// a change while a reply is in progress. One listener serves every logo.
const reducedMotionQuery =
  typeof window !== "undefined"
    ? window.matchMedia?.("(prefers-reduced-motion: reduce)")
    : undefined;
const reduceMotion = ref(Boolean(reducedMotionQuery?.matches));
reducedMotionQuery?.addEventListener("change", (event) => {
  reduceMotion.value = event.matches;
});

const LARGE_STAR =
  "m246.3 328.1-17.8 41.2c-6.4 14.8-26.9 14.8-33.3 0l-17.8-41.2c-14.9-34.2-41.8-61.4-75.3-76.3l-48.8-21.6c-14.7-6.5-14.7-27.9 0-34.4l47.2-21c34.4-15.3 61.7-43.5 76.4-78.8l18-43.7c6.3-15.2 27.3-15.2 33.6 0l18 43.7c14.7 35.3 42 63.6 76.4 78.8l47.2 21c14.7 6.5 14.7 27.9 0 34.4l-48.8 21.6c-33.5 14.8-60.4 42.1-75.3 76.2z";
const SMALL_STAR =
  "m402.2 449.3-5.3 12.2c-3.5 7.9-14.4 7.9-17.9 0l-5.3-12.2c-8.4-19.3-23.6-34.6-42.4-43l-15.4-6.9c-7.9-3.5-7.9-14.9 0-18.4l14.5-6.5c19.4-8.6 34.8-24.5 43.1-44.5l5.4-13.1c3.4-8.1 14.6-8.1 18 0l5.4 13.1c8.3 19.9 23.7 35.8 43.1 44.5l14.5 6.5c7.9 3.5 7.9 14.9 0 18.4l-15.4 6.9c-19 8.3-34.1 23.7-42.5 43z";

// A tilted orbit around the large star: the first half swings down in front
// and grows, the second half shrinks behind. Each point is [x, y, scale].
const ORBIT_POINTS = [
  [20.58, 6.14, 1],
  [20.78, 8.09, 1.1],
  [19.51, 10.38, 1.18],
  [17.08, 13.14, 1.23],
  [13.86, 15.93, 1.25],
  [10.34, 18.34, 1.23],
  [7.06, 20, 1.18],
  [4.52, 20.65, 1.1],
  [3.1, 20.2, 1],
  [3.02, 18.71, 0.9],
  [4.29, 16.42, 0.82],
  [6.72, 13.66, 0.77],
  [9.94, 10.87, 0.75],
  [13.46, 8.46, 0.77],
  [16.74, 6.8, 0.82],
  [19.28, 6.15, 0.9],
  [20.58, 6.14, 1],
];
const ORBIT = {
  translate: ORBIT_POINTS.map(([x, y]) => `${x} ${y}`).join(";"),
  scale: ORBIT_POINTS.map(([, , s]) => s).join(";"),
};
const LOOP = { dur: "2.8s", repeatCount: "indefinite" };

// Drawing order in the mask: far copy, large star, near copy.
const COPIES = [
  { name: "far", attrs: { fill: "#8c8c8c" }, visibility: "hidden;visible" },
  { name: "large" },
  {
    name: "near",
    attrs: { fill: "white", stroke: "black" },
    visibility: "visible;hidden",
  },
];

// A wave edge (period 12) wide enough to drift a full period, closed below.
const WAVE = `M-26 0 q3 -2 6 0${" t6 0".repeat(11)} V60 H-26 Z`;

// One 5.6 s tide cycle is two orbits. Both tides reset while everything is
// blue, centred on the orbit's start, so the small star then rests at the
// top right.
const TIDES = [
  {
    name: "gold",
    top: "#ffe08a",
    bottom: "#f5a623",
    rise: "0;0.06;0.45;1",
    drift: "0 0;12 0",
  },
  {
    name: "blue",
    top: "#4aa3dc",
    bottom: "#2f86bd",
    rise: "0;0.5;0.94;1",
    drift: "0 0;-12 0",
  },
];
</script>

<script setup lang="ts">
import { computed } from "vue";

// The AstrBot mark: a large star and a small one. While a reply is in progress
// the small star circles the large one on a tilted orbit, passing behind and in
// front of it, while gold and blue tides take turns rising through both. At
// rest it is the plain mark, without masks or animation elements.
const props = defineProps<{
  // A reply is in progress.
  animated?: boolean;
}>();

const moving = computed(() => Boolean(props.animated) && !reduceMotion.value);

// Several logos share a page, so each needs its own element ids.
const uid = `chatui-logo-${++logoCount}`;
</script>
