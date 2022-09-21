if exists("b:current_syntax")
  finish
endif


syntax match EdirCounter /\v^\d+\ze	/
syntax match EdirComment /\v^\s+#/

highlight default link EdirCounter SpecialKey
highlight default link EdirComment Comment

let b:current_syntax = "edir"

