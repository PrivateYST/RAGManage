import antfu from '@antfu/eslint-config'

export default antfu(
  {
    typescript: true,
    vue: true,
    // Prettier is the repository's source formatter; disable antfu's overlapping
    // stylistic fixer so lint remains focused on correctness and Vue/TypeScript rules.
    stylistic: false,
    ignores: ['docs/**'],
  },
  {
    rules: {
      // Prettier owns SFC whitespace and void-element formatting in this repository.
      'vue/html-closing-bracket-newline': 'off',
      'vue/html-indent': 'off',
      'vue/html-self-closing': 'off',
      'vue/multiline-html-element-content-newline': 'off',
      'vue/singleline-html-element-content-newline': 'off',
    },
  },
)
