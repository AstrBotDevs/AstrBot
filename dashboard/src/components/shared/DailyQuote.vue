<template>
  <div class="daily-quote">
    <div
      class="quote-text"
      :style="{ color: 'var(--v-theme-on-surface)', opacity: 0.75 }"
    >
      "{{ currentQuote.text }}"
    </div>
    <div
      class="quote-author"
      :style="{ color: 'var(--v-theme-on-surface)', opacity: 0.5 }"
    >
      — {{ currentQuote.author }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from "vue";
import { useI18n } from "@/i18n/composables";
import type { Locale } from "@/i18n/types";

const { locale } = useI18n();

interface Quote {
  text: string;
  author: string;
}

const quotes: Record<Locale, Quote[]> = {
  "en-US": [
    {
      text: "The best way to predict the future is to create it.",
      author: "Peter Drucker",
    },
    {
      text: "Code is like humor. When you have to explain it, it's bad.",
      author: "Cory House",
    },
    {
      text: "First, solve the problem. Then, write the code.",
      author: "John Johnson",
    },
    { text: "Simplicity is the soul of efficiency.", author: "Austin Freeman" },
    { text: "Make it work, make it right, make it fast.", author: "Kent Beck" },
    {
      text: "The only way to learn a new programming language is by writing programs in it.",
      author: "Dennis Ritchie",
    },
    {
      text: "Sometimes it pays to stay in bed on Monday, rather than spending the rest of the week debugging Monday's code.",
      author: "Dan Salomon",
    },
    {
      text: "Measuring programming progress by lines of code is like measuring aircraft building progress by weight.",
      author: "Bill Gates",
    },
    {
      text: "Walking on water and developing software from a specification are easy if both are frozen.",
      author: "Edward V. Berard",
    },
    { text: "It works on my machine.", author: "Every Developer" },
    { text: "Talk is cheap. Show me the code.", author: "Linus Torvalds" },
    {
      text: "Any fool can write code that a computer can understand. Good programmers write code that humans can understand.",
      author: "Martin Fowler",
    },
    {
      text: "Programming is not about typing, it's about thinking.",
      author: "Cathy Apple",
    },
    { text: "Deleted code is debugged code.", author: "Jeff Sickel" },
    {
      text: "The most disastrous thing you can learn is your first programming language.",
      author: "Alan Kay",
    },
  ],
  "zh-CN": [
    { text: "预测未来的最好方式是创造未来。", author: "彼得·德鲁克" },
    {
      text: "代码就像笑话，当你需要解释的时候，它就不好了。",
      author: "科里·豪斯",
    },
    { text: "先解决问题，再写代码。", author: "约翰·约翰逊" },
    { text: "简单是效率的灵魂。", author: "奥斯汀·弗里曼" },
    { text: "让它工作，让它正确，让它快速。", author: "肯特·贝克" },
    { text: "学习新编程语言的唯一方法是用它写程序。", author: "丹尼斯·里奇" },
    {
      text: "有时候周一躺在床上比花一周时间调试周一的代码更划算。",
      author: "丹·萨洛蒙",
    },
    {
      text: "用代码行数衡量编程进度就像用重量衡量飞机建造进度一样。",
      author: "比尔·盖茨",
    },
    {
      text: "在水上行走和根据规格说明开发软件都很容易——如果两者都是冻结的话。",
      author: "爱德华·V·贝拉德",
    },
    { text: "在我机器上能运行。", author: "每个开发者" },
    { text: "空谈便宜。给我看代码。", author: "林纳斯·托瓦兹" },
    {
      text: "任何傻瓜都能写出计算机能理解的代码。好的程序员写的是人类能理解的代码。",
      author: "马丁·福勒",
    },
    { text: "编程不是关于打字，是关于思考。", author: "凯西·阿普尔" },
    { text: "删除的代码就是调试过的代码。", author: "杰夫·西克尔" },
    {
      text: "你学第一门编程语言时学到的东西往往是最具灾难性的。",
      author: "艾伦·凯伊",
    },
  ],
  "ru-RU": [
    {
      text: "Лучший способ предсказать будущее — создать его.",
      author: "Питер Друкер",
    },
    {
      text: "Код как шутка. Когда нужно объяснять — значит плохо.",
      author: "Кори Хаус",
    },
    { text: "Сначала реши проблему. Потом пиши код.", author: "Джон Джонсон" },
    { text: "Простота — душа эффективности.", author: "Остин Фриман" },
    { text: "Сделай, чтобы работало, правильно, быстро.", author: "Кент Бек" },
    {
      text: "Единственный способ выучить новый язык программирования — писать на нём программы.",
      author: "Деннис Ритчи",
    },
    {
      text: "Иногда выгоднее понедельник проспать, чем неделю отлаживать код понедельника.",
      author: "Дэн Саломон",
    },
    {
      text: "Измерять прогресс программирования строками кода — как измерять постройку самолёта весом.",
      author: "Билл Гейтс",
    },
    {
      text: "Ходить по воде и разрабатывать ПО по спецификации легко, если оба заморожены.",
      author: "Эдвард В. Берард",
    },
    { text: "На моей машине работает.", author: "Каждый разработчик" },
    { text: "Разговоры дёшевы. Покажи мне код.", author: "Линус Торвальдс" },
    {
      text: "Любой дурак может написать код, который поймёт компьютер. Хорошие программисты пишут код, который поймут люди.",
      author: "Мартин Фаулер",
    },
    {
      text: "Программирование — это не о печатании, а о мышлении.",
      author: "Кэти Эппл",
    },
    { text: "Удалённый код — это отлаженный код.", author: "Джефф Сайкел" },
    {
      text: "Самое катастрофическое, что можно выучить — свой первый язык программирования.",
      author: "Алан Кей",
    },
  ],
};

const currentQuote = ref<Quote>({ text: "", author: "" });

const getQuoteOfTheDay = (): Quote => {
  const lang = locale.value || "en-US";
  const langQuotes = quotes[lang] || quotes["en-US"];
  // Use date as seed so the quote stays the same for the whole day
  const today = new Date();
  const dayOfYear = Math.floor(
    (today.getTime() - new Date(today.getFullYear(), 0, 0).getTime()) /
      86400000,
  );
  const index = dayOfYear % langQuotes.length;
  return langQuotes[index];
};

// Update quote when locale changes
watch(
  locale,
  () => {
    currentQuote.value = getQuoteOfTheDay();
  },
  { immediate: true },
);
</script>

<style scoped>
.daily-quote {
  text-align: left;
  padding: 8px 16px;
  max-width: 100%;
}

.quote-text {
  font-size: 14px;
  font-style: italic;
  line-height: 1.5;
  margin-bottom: 4px;
}

.quote-author {
  font-size: 12px;
  opacity: 0.5;
}
</style>
