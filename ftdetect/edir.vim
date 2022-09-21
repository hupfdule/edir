augroup edir
  au!
  au BufRead,BufNewFile edir*,dir* call s:detect_edir()
augroup END

""
" Set the file type to 'edir' if the first 3 non-blank lines match the
" format a normal edir buffer.
function! s:detect_edir() abort
  for i in range (1, 3)
    let lnum = nextnonblank(i)
    if lnum ==# 0
      break
    endif
    let match = match(getline(lnum), g:edir#pattern_line)
    if match == -1
      return
    endif
  endfor

  setf edir
endfunction

