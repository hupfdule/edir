" Plugin folklore "{{{2
if v:version < 700 || exists('b:did_ftplugin')
  finish
endif
let b:did_ftplugin = 1

let s:cpo_save = &cpo
"}}}2

" === User options ======================================================= {{{1

""
" The format of the virtual text displaying the file info.
let g:edir_file_info_format = get(g:, 'edir_file_info_format', '{filename} {size} {owner} {timestamp}')

""
" Whether to show the file info as virtual text.
" 0 = don't show file info
" 1 = show file info for currently selected file
" 2 = show file info for all files
let g:edir_show_file_info = get(g:, 'edir_show_file_info', 2)

" === User options end =================================================== }}}1

" Maps counter to the file info
let b:edir_file_info = {}

" Load all the file info when loading the buffer
call edir#load_file_info()

" Set the tabstop width to the optimal amount
let match = matchlist(getline('$'), g:edir#pattern_line)
if match != []
  let max_num = strchars(match[1])
  execute 'setlocal tabstop=' . (max_num + 2)
endif

" On each movement update the virtual text with the file info
augroup edir
  autocmd!
  autocmd CursorMoved * :call edir#update_file_info()
augroup END

" Show the file info for the current entry
call edir#update_file_info()

" Plugin folklore "{{{2
let &cpo = s:cpo_save
unlet s:cpo_save
"}}}2

" Vim Modeline " {{{3
" vim: set foldmethod=marker:
