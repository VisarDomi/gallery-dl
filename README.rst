modified it to work only with hitomi, and download thumbnails as well.

it has breaking changes, so it will not work with the original gallery-dl formatting.

unless you set formatting to this:

```
filename_fmt = "{category}_{gallery_id}_{filename}.{extension}"
```

```
page_str = f"{i:>04}"
```

so basically old formatting, but with 4 padding to the auto generated number.
thumbnails will have thumb somewhere in the filename:

```
"filename": f"thumb_{page_str}"
```
