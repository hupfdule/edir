"" Pattern for a single line in the edir buffer
let g:edir#pattern_line  = '\v^'             " start with
let g:edir#pattern_line .= '%(\s*#\s*)?'     " optional comment character
let g:edir#pattern_line .= '(\d+)'           " then the counter
let g:edir#pattern_line .= '\t'              " then a tab
let g:edir#pattern_line .= '(.*)$'           " end with the file name

silent! let s:log = log#getLogger(expand('<sfile>:t'))


""
" Load the file info for every line in the buffer.
"
" The file info is loaded by calling the 'g:edir_info_command' for each
" file name in the buffer. The result is stored in the buffer-local map
" 'b:edir_file_info'
function! edir#load_file_info() abort
  silent! call s:log.trace("[edir#load_file_info] started")
  for lnum in range(1, line('$'))
    let l:match = matchlist(getline(lnum), g:edir#pattern_line)
    if l:match !=# []
      silent! call s:log.trace("[edir#load_file_info] get_edir_file_info start ")
      let l:counter  = l:match[1]
      let l:filename = l:match[2]
      " in vim (but not neovim) this blocks the UI until all fileinfos are
      " gathered. This should be done sequentially like in vim-tree. Then
      " it should be possible to use the UI while the info is still updated.
      call timer_start(0, function('s:trigger_get_file_info', [l:counter, l:filename]))
      silent! call s:log.trace("[edir#load_file_info] get_edir_file_info end ")
    endif
  endfor
  silent! call s:log.trace("[edir#load_file_info] triggered")
  call edir#update_file_info()
  silent! call s:log.trace("[edir#load_file_info] finished rendering")
endfunction


""
" Get the file info for the given 'file'.
"
" A dict with the file info will be returned. If any value could not be
" retrieved it will be omitted in the returned dict.
"
" @param file: The (absolute or relative) filename of the file for which to
"              provide the file info
" @returns A dict with the following fields:
"          'filename':          the (absolute or relative) filename of the file
"          'size':              the size of the file in human readable form
"          'bytesize':          the size of the file in bytes
"          'permissions_octal': the permission bits in octal form
"          'permissions':       the permission bits in human readable form (like 'ls')
"          'timestamp':         the modification timestamp in the form yyyy-MM-dd HH:mm:ss
"          'owner':             the owner of the file
"          'group':             the group of the file
function! s:get_edir_file_info(file) abort
  let file_info = {}
  let du   = system('du -sh ' . shellescape(a:file))
  if v:shell_error ==# 0
    let du_split = split(du, '\t')
    let file_info['size']     = get(du_split, 0, v:null)
  endif

  let fixed_width_info = system('stat --printf="%a\t%A\t%.19y\t%U\t%G\t%s\t%n" ' . shellescape(a:file))
  if v:shell_error ==# 0
    let fixed_width_info_split = split(fixed_width_info, '\t')
    let file_info['permissions_octal'] = get(fixed_width_info_split, 0, v:null)
    let file_info['permissions']       = get(fixed_width_info_split, 1, v:null)
    let file_info['timestamp']         = get(fixed_width_info_split, 2, v:null)
    let file_info['owner']             = get(fixed_width_info_split, 3, v:null)
    let file_info['group']             = get(fixed_width_info_split, 4, v:null)
    let file_info['bytesize']          = get(fixed_width_info_split, 5, v:null)
    let file_info['filename']          = get(fixed_width_info_split, 6, v:null)
  endif
  return filter(file_info, 'v:val != v:null')
endfunction


function! s:trigger_get_file_info(counter, filename, timer_id) abort
  silent! call s:log.trace("[s:trigger_get_file_info] getting actual file info for '" . a:filename ."' with timer " . a:timer_id)
  let l:fileinfo = s:format_file_info(s:get_edir_file_info(a:filename))
  let b:edir_file_info[a:counter] = l:fileinfo
  silent! call s:log.trace("[s:trigger_get_file_info] starting rendering with timer " . a:timer_id)
  call edir#update_file_info()
  silent! call s:log.trace("[s:trigger_get_file_info] finished rendering with timer " . a:timer_id)
endfunction


""
" Return a formatted string for the given 'file_info'.
"
" The formatted string will adhere to the format specified in
" 'g:edir_file_info_format'.
"
" @param file_info: the file info dict as returned by 's:get_edir_file_info'.
" @returns the formatted string for the given file info.
function! s:format_file_info(file_info) abort
  let formatted_info = g:edir_file_info_format
  for item in items(a:file_info)
    let formatted_info = substitute(formatted_info, '{'.item[0].'}', item[1], '')
  endfor
  return formatted_info
endfunction


""
" Update the displayed file info.
"
" That is displaying the file info as virtual text.
" This methods takes the value of 'g:edir_show_file_info' into account.
"   0: Don't show any file info as virtual text
"   1: Show the file info for the currently selected line
"   2: Show the file info for all the files in the buffer
function! edir#update_file_info() abort
  if g:edir_show_file_info ==# 0
    let l:lnums = []
  elseif g:edir_show_file_info ==# 1
    let l:lnums = [line('.')]
  else
    let l:lnums = range(1, line('$'))
  endif

  if has('nvim')
    " First remove all virtual text
    for l:lnum in range(1, line('$'))
      let ns_id = v:lua.vim.api.nvim_create_namespace('edir')
      call v:lua.vim.api.nvim_buf_del_extmark(0, ns_id, l:lnum)
    endfor
    " then redraw the requested ones
    for l:lnum in l:lnums
      call s:nvim_update_file_info(l:lnum)
    endfor
  elseif has('textprop')
    if index(prop_type_list(), 'file_info') ==# -1
      call prop_type_add('file_info', {'highlight': 'Comment'})
    endif
    " First remove all virtual text
    call prop_remove({'type': 'file_info', 'all':v:true})
    " then redraw the requested ones
    for l:lnum in l:lnums
      call s:vim_update_file_info(l:lnum)
    endfor
  endif
endfunction


""
" Update the file info for the current line (if using neovim).
"
" Uses the extmarks of neovim for displaying the file info as virtual text.
function! s:nvim_update_file_info(lnum) abort
  let id=998
  let l:match = matchlist(getline(a:lnum), g:edir#pattern_line)
  if l:match == []
    let file_info = ''
  else
    let file_info = get(b:edir_file_info, l:match[1], '')
  endif
  let ns_id = v:lua.vim.api.nvim_create_namespace('edir')
  let show_file_info = get(g:, 'edir_show_file_info', 0)
  "if show_file_info ==# 1
  "  let extmark_id = 998
  "elseif show_file_info ==# 2
    let extmark_id = a:lnum
  "else
  "  " should never happen
  "  return
  "endif
  call v:lua.vim.api.nvim_buf_set_extmark(0, ns_id, a:lnum-1, 0, {'id':extmark_id, 'virt_text':[[file_info, "Comment"]], 'virt_text_pos':'right_align'})
endfunction


""
" Update the file info for the current line (if using vim).
"
" Uses the textprop feature of vim for displaying the file info as virtual text.
function! s:vim_update_file_info(lnum) abort
  let l:match = matchlist(getline(a:lnum), g:edir#pattern_line)
  if l:match == []
    let file_info = ''
  else
    let file_info = get(b:edir_file_info, l:match[1], '')
  endif
  let b:current_prop_id = prop_add(a:lnum, 0, {'type': 'file_info', 'text': file_info, 'text_align': 'right'})
endfunction

